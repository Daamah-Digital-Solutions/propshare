import { CheckCircle, Circle, Clock } from "lucide-react";
import type { PropertyMilestone } from "@/lib/api";

// Phase 15b: this surface is now driven by REAL per-property milestones
// (property_milestones, embedded in the property detail). The previous hardcoded
// 8-event array ("Property Listed / Oct 15, 2024" …) has been retired — every
// property used to show the same fake timeline.

type DisplayStatus = "completed" | "current" | "upcoming";

const toDisplayStatus = (s: PropertyMilestone["status"]): DisplayStatus =>
  s === "completed" ? "completed" : s === "in_progress" ? "current" : "upcoming";

// "Jun 2026" from an ISO date; honest "TBD" when no date is set.
const fmtDate = (iso: string | null): string => {
  if (!iso) return "TBD";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "TBD";
  return d.toLocaleDateString("en-US", { month: "short", year: "numeric" });
};

const PropertyTimeline = ({ milestones = [] }: { milestones?: PropertyMilestone[] }) => {
  const events = [...milestones].sort((a, b) => a.sort_index - b.sort_index);

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-xl font-semibold text-foreground">Project Timeline</h3>
        <p className="text-sm text-muted-foreground mt-1">
          Track the progress of this investment opportunity
        </p>
      </div>

      {events.length === 0 ? (
        <div className="bg-card rounded-xl p-8 border border-border border-dashed text-center">
          <p className="text-sm text-muted-foreground">
            No project milestones have been published yet.
          </p>
        </div>
      ) : (
        <div className="relative">
          {/* Timeline Line */}
          <div className="absolute left-5 top-0 bottom-0 w-0.5 bg-border" />

          <div className="space-y-6">
            {events.map((event) => {
              const status = toDisplayStatus(event.status);
              const date =
                event.status === "completed" && event.completed_at
                  ? fmtDate(event.completed_at)
                  : fmtDate(event.target_date);
              return (
                <div key={event.id} className="relative flex gap-4">
                  {/* Status Icon */}
                  <div className="relative z-10">
                    {status === "completed" ? (
                      <div className="w-10 h-10 bg-success rounded-full flex items-center justify-center">
                        <CheckCircle size={20} className="text-success-foreground" />
                      </div>
                    ) : status === "current" ? (
                      <div className="w-10 h-10 bg-primary rounded-full flex items-center justify-center animate-pulse">
                        <Clock size={20} className="text-primary-foreground" />
                      </div>
                    ) : (
                      <div className="w-10 h-10 bg-secondary border-2 border-border rounded-full flex items-center justify-center">
                        <Circle size={16} className="text-muted-foreground" />
                      </div>
                    )}
                  </div>

                  {/* Content */}
                  <div className={`flex-1 pb-6 ${status === "upcoming" ? "opacity-60" : ""}`}>
                    <div className="bg-card rounded-xl p-4 border border-border">
                      <div className="flex items-start justify-between gap-4">
                        <div>
                          <h4 className="font-semibold text-foreground">{event.title}</h4>
                          {event.description && (
                            <p className="text-sm text-muted-foreground mt-1">
                              {event.description}
                            </p>
                          )}
                          {status === "current" && event.progress_pct != null && (
                            <p className="text-xs text-primary font-medium mt-1">
                              {event.progress_pct}% complete
                            </p>
                          )}
                        </div>
                        <span
                          className={`text-sm whitespace-nowrap ${
                            status === "current" ? "text-primary font-medium" : "text-muted-foreground"
                          }`}
                        >
                          {date}
                        </span>
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Legend */}
      <div className="flex flex-wrap gap-6 pt-4 border-t border-border">
        <div className="flex items-center gap-2 text-sm">
          <div className="w-4 h-4 bg-success rounded-full" />
          <span className="text-muted-foreground">Completed</span>
        </div>
        <div className="flex items-center gap-2 text-sm">
          <div className="w-4 h-4 bg-primary rounded-full" />
          <span className="text-muted-foreground">In Progress</span>
        </div>
        <div className="flex items-center gap-2 text-sm">
          <div className="w-4 h-4 bg-secondary border-2 border-border rounded-full" />
          <span className="text-muted-foreground">Upcoming</span>
        </div>
      </div>
    </div>
  );
};

export default PropertyTimeline;
