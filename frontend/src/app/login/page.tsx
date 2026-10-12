import { AuthShell } from "@/components/auth/AuthShell";
import { LoginForm } from "@/components/auth/LoginForm";
import { ShowcaseHero, ShowcaseHighlights } from "@/components/auth/Showcase";

// The sign-in page is the product's showcase: the promise, Microsoft sign-in,
// and a preview drawn from made-up data (nothing is fetched before sign-in).
export default function LoginPage() {
  return (
    <AuthShell
      below={<ShowcaseHighlights />}
      footnote="Internal tool. Sample data shown."
    >
      <ShowcaseHero action={<LoginForm />} />
    </AuthShell>
  );
}
