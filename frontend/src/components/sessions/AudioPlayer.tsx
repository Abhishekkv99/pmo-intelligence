"use client";

import { useImperativeHandle, useRef, useState, type Ref } from "react";
import { useMediaUrl } from "@/hooks/useSessions";

export interface AudioPlayerHandle {
  /** Jump to `ms` into the recording and play from there. */
  seek: (ms: number) => void;
}

/**
 * The call's recording. The URL lasts 15 minutes (presigned on S3, a signed
 * backend link locally), so a fresh one is fetched when the player reports an
 * error, once, keeping the position.
 */
export function AudioPlayer({
  sessionId,
  ref,
}: {
  sessionId: string;
  ref?: Ref<AudioPlayerHandle>;
}) {
  const audio = useRef<HTMLAudioElement>(null);
  const { media, error, refresh } = useMediaUrl(sessionId);
  const [gaveUp, setGaveUp] = useState(false);
  const refreshed = useRef(false);

  useImperativeHandle(
    ref,
    () => ({
      seek(ms: number) {
        const element = audio.current;
        if (!element) return;
        element.currentTime = ms / 1000;
        void element.play().catch(() => undefined);
      },
    }),
    [],
  );

  if (error || gaveUp) {
    return (
      <p className="text-sm text-muted-foreground">
        The recording could not be loaded.
      </p>
    );
  }
  return (
    <audio
      ref={audio}
      controls
      preload="metadata"
      src={media?.url}
      className="w-full"
      aria-label="Call recording"
      data-testid="session-audio"
      onError={() => {
        if (refreshed.current) {
          setGaveUp(true);
          return;
        }
        refreshed.current = true;
        const position = audio.current?.currentTime ?? 0;
        void refresh().then(() => {
          if (audio.current) audio.current.currentTime = position;
        });
      }}
    />
  );
}
