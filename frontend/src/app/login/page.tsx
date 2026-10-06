import { LoginForm } from "@/components/auth/LoginForm";
import { APP_NAME, APP_TAGLINE } from "@/lib/constants";

export default function LoginPage() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-muted/40 p-4">
      <div className="mb-8 text-center">
        <h1 className="text-3xl font-bold">{APP_NAME}</h1>
        <p className="mt-2 text-muted-foreground">{APP_TAGLINE}</p>
      </div>
      <LoginForm />
    </div>
  );
}
