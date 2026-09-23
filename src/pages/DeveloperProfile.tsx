import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowLeft,
  Building2,
  CheckCircle2,
  ExternalLink,
  Globe,
  Star,
  TrendingUp,
  Users,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import PropertyGrid from "@/components/marketplace/PropertyGrid";
import { ApiError, assetUrl, developerApi } from "@/lib/api";
import { toMarketplaceProperty } from "@/lib/properties";

/**
 * Public developer profile — opened by "View Profile" on a property page.
 *
 * Everything shown is either something the admin entered for this developer (name, logo,
 * about, website, rating, projects) or a live figure computed from the developer's PUBLIC
 * listings on this platform. A field that was never filled is simply not rendered: the page
 * never invents a bio, a rating or a track record.
 */

const money = (n: number) =>
  n >= 1_000_000
    ? `$${(n / 1_000_000).toLocaleString(undefined, { maximumFractionDigits: 1 })}M`
    : `$${Math.round(n).toLocaleString()}`;

export default function DeveloperProfile() {
  const { slug = "" } = useParams<{ slug: string }>();
  const { data, isLoading, error } = useQuery({
    queryKey: ["developer", slug],
    queryFn: () => developerApi.get(slug),
    enabled: Boolean(slug),
    retry: (count, err) => !(err instanceof ApiError && err.status === 404) && count < 2,
  });

  if (isLoading) {
    return (
      <div className="container mx-auto px-4 py-24 text-center text-muted-foreground">
        Loading developer…
      </div>
    );
  }

  if (error || !data) {
    const notFound = error instanceof ApiError && error.status === 404;
    return (
      <div className="container mx-auto px-4 py-24 text-center" data-testid="developer-missing">
        <Building2 className="mx-auto mb-4 h-10 w-10 text-muted-foreground" />
        <h1 className="text-2xl font-semibold text-foreground">
          {notFound ? "Developer not found" : "Could not load this developer"}
        </h1>
        <p className="mt-2 text-muted-foreground">
          {notFound
            ? "This developer has no public listings on Capimax PropShare right now."
            : "Please try again in a moment."}
        </p>
        <Button asChild variant="outline" className="mt-6">
          <Link to="/marketplace">Browse the marketplace</Link>
        </Button>
      </div>
    );
  }

  const name = data.name || "Developer";
  const logo = data.logo ? assetUrl(data.logo) : "";
  const cards = data.properties.map(toMarketplaceProperty);
  const s = data.stats;

  const stats = [
    { icon: Building2, label: "Listings on PropShare", value: String(s.listings) },
    { icon: TrendingUp, label: "Raised on PropShare", value: money(s.total_raised) },
    { icon: Users, label: "Investors", value: s.investors.toLocaleString() },
    { icon: CheckCircle2, label: "Fully funded", value: String(s.funded) },
  ];

  return (
    <div className="min-h-screen bg-background">
      <section className="bg-gradient-to-br from-primary/10 via-background to-secondary/10">
        <div className="container mx-auto px-4 py-10 md:py-14">
          <Link
            to="/marketplace"
            className="mb-6 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
          >
            <ArrowLeft className="h-4 w-4" /> Marketplace
          </Link>

          <div className="flex flex-col gap-6 md:flex-row md:items-center">
            {logo ? (
              <img
                src={logo}
                alt={name}
                className="h-24 w-24 rounded-2xl border border-border bg-white object-cover"
              />
            ) : (
              <div
                aria-hidden
                className="flex h-24 w-24 items-center justify-center rounded-2xl bg-primary/10 text-4xl font-semibold text-primary"
              >
                {name.charAt(0).toUpperCase()}
              </div>
            )}
            <div className="flex-1">
              <p className="text-sm font-medium uppercase tracking-wide text-primary">Developer</p>
              <h1 className="mt-1 text-3xl font-bold text-foreground md:text-4xl">{name}</h1>
              <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-2 text-sm text-muted-foreground">
                {data.rating != null && (
                  <span className="flex items-center gap-1" title="Capimax's own assessment">
                    <Star className="h-4 w-4 fill-warning text-warning" /> {data.rating} / 5
                  </span>
                )}
                {data.projects_completed != null && (
                  <span>{data.projects_completed.toLocaleString()} projects completed</span>
                )}
                {data.website && (
                  <a
                    href={data.website}
                    target="_blank"
                    rel="noopener noreferrer nofollow"
                    className="flex items-center gap-1 text-primary hover:underline"
                  >
                    <Globe className="h-4 w-4" />
                    {data.website.replace(/^https?:\/\/(www\.)?/, "").replace(/\/$/, "")}
                    <ExternalLink className="h-3 w-3" />
                  </a>
                )}
              </div>
            </div>
          </div>
        </div>
      </section>

      <div className="container mx-auto space-y-10 px-4 py-10">
        <div className="grid grid-cols-2 gap-4 md:grid-cols-4" data-testid="developer-stats">
          {stats.map((st) => (
            <Card key={st.label}>
              <CardContent className="p-5">
                <st.icon className="mb-2 h-5 w-5 text-primary" />
                <div className="text-2xl font-bold text-foreground">{st.value}</div>
                <div className="text-sm text-muted-foreground">{st.label}</div>
              </CardContent>
            </Card>
          ))}
        </div>

        {data.about && (
          <section>
            <h2 className="mb-3 text-xl font-semibold text-foreground">About {name}</h2>
            <div className="max-w-3xl space-y-3 leading-relaxed text-muted-foreground">
              {data.about.split(/\n{2,}/).map((para, i) => (
                <p key={i}>{para}</p>
              ))}
            </div>
          </section>
        )}

        <section>
          <h2 className="mb-4 text-xl font-semibold text-foreground">
            Properties by {name} on PropShare
          </h2>
          <PropertyGrid properties={cards} viewMode="grid" />
        </section>

        <p className="text-xs text-muted-foreground">
          Figures cover this developer's listings on Capimax PropShare only. Ratings and project
          counts are provided by Capimax and are not a recommendation to invest.
        </p>
      </div>
    </div>
  );
}
