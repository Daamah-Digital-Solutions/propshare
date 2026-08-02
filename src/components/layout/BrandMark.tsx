import { Link } from "react-router-dom";

/**
 * Brand lockup: the emblem + a CRISP text wordmark so the platform name
 * "Capimax PropShare" is always legible. The raster wordmark (capimax-logo.png)
 * renders its "PropShare" line so small at header sizes that the name is
 * unreadable — this renders the name as real text (emblem · Capimax · PropShare)
 * so it stays sharp at any size and reads consistently with the brand identity.
 */
export function BrandMark({ className = "" }: { className?: string }) {
  return (
    <Link
      to="/"
      className={`flex items-center gap-2 min-w-0 ${className}`}
      aria-label="Capimax PropShare"
    >
      <img
        src="/icon-192.png"
        alt=""
        aria-hidden="true"
        className="h-8 w-8 flex-shrink-0"
      />
      <span className="flex flex-col leading-none">
        <span className="text-base font-bold tracking-tight text-foreground">Capimax</span>
        <span className="text-[10px] font-semibold uppercase tracking-[0.22em] text-primary">
          PropShare
        </span>
      </span>
    </Link>
  );
}

export default BrandMark;
