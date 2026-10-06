"use client";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { useSSOLogin } from "@/hooks/useSSOLogin";

export function LoginForm() {
  const { initiateSSO, isLoading: ssoLoading, error: ssoError } = useSSOLogin();

  return (
    <Card className="w-full max-w-md">
      <CardHeader className="text-center">
        <CardTitle className="text-2xl">Sign In</CardTitle>
        <CardDescription>
          Use your work Microsoft account to access the platform
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {ssoError && (
          <div className="rounded-md bg-destructive/10 p-3 text-sm text-destructive">
            {ssoError}
          </div>
        )}
      </CardContent>
      <CardFooter className="flex flex-col gap-4">
        <Button
          type="button"
          className="w-full"
          disabled={ssoLoading}
          onClick={() => void initiateSSO()}
        >
          {ssoLoading ? "Redirecting..." : "Sign in with Microsoft"}
        </Button>
        <p className="text-center text-sm text-muted-foreground">
          Accounts are managed in Microsoft Entra ID. Ask your administrator if
          you need access.
        </p>
      </CardFooter>
    </Card>
  );
}
