import { Link } from "react-router-dom";
import { Compass } from "lucide-react";
import { PageContainer } from "@/components/layout/page";
import { Button } from "@/components/ui/button";

export default function NotFoundPage() {
  return (
    <div className="grid min-h-[60vh] place-items-center">
      <PageContainer className="text-center">
        <Compass className="mx-auto size-9 text-dim" />
        <h1 className="mt-4 text-2xl font-semibold tracking-tight text-foreground">Not found</h1>
        <p className="mx-auto mt-2 max-w-sm text-sm leading-relaxed text-dim">
          This screen doesn't exist in the workspace. Check the address, or head back to the dashboard.
        </p>
        <div className="mt-5 flex justify-center gap-2">
          <Link to="/app"><Button>Go to dashboard</Button></Link>
          <Link to="/app/cases"><Button variant="ghost">Browse cases</Button></Link>
        </div>
      </PageContainer>
    </div>
  );
}