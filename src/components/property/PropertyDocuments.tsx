import { FileText, Download, Eye, Lock, CheckCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

const documents = [
  {
    id: 1,
    name: "Property Valuation Report",
    type: "PDF",
    size: "2.4 MB",
    date: "Dec 2024",
    status: "verified",
    public: true,
  },
  {
    id: 2,
    name: "Title Deed",
    type: "PDF",
    size: "1.2 MB",
    date: "Nov 2024",
    status: "verified",
    public: true,
  },
  {
    id: 3,
    name: "SPV Formation Documents",
    type: "PDF",
    size: "3.8 MB",
    date: "Oct 2024",
    status: "verified",
    public: true,
  },
  {
    id: 4,
    name: "Investment Memorandum",
    type: "PDF",
    size: "5.1 MB",
    date: "Dec 2024",
    status: "verified",
    public: true,
  },
  {
    id: 5,
    name: "Financial Projections",
    type: "XLSX",
    size: "856 KB",
    date: "Dec 2024",
    status: "verified",
    public: false,
  },
  {
    id: 6,
    name: "Property Insurance Certificate",
    type: "PDF",
    size: "1.5 MB",
    date: "Jan 2025",
    status: "pending",
    public: false,
  },
  {
    id: 7,
    name: "Rental Income History",
    type: "PDF",
    size: "920 KB",
    date: "Dec 2024",
    status: "verified",
    public: true,
  },
  {
    id: 8,
    name: "Building Inspection Report",
    type: "PDF",
    size: "4.2 MB",
    date: "Nov 2024",
    status: "verified",
    public: true,
  },
];

const PropertyDocuments = () => {
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-xl font-semibold text-foreground">Property Documents</h3>
          <p className="text-sm text-muted-foreground mt-1">
            All documents have been verified by our legal team
          </p>
        </div>
        <Button variant="outline" size="sm" disabled>
          <Download size={16} className="mr-2" />
          Download All
        </Button>
      </div>

      {/* Documents are deferred to a standalone phase (needs app storage). The listing
          below is illustrative; downloads are not available yet — honest-disabled, not removed. */}
      <div className="bg-amber-500/10 border border-amber-500/30 rounded-xl p-4 text-sm text-amber-700 dark:text-amber-400">
        Document downloads are not available yet. This feature is coming in a future release.
      </div>

      <div className="bg-card rounded-2xl border border-border overflow-hidden">
        <div className="divide-y divide-border">
          {documents.map((doc) => (
            <div 
              key={doc.id} 
              className="flex items-center justify-between p-4 hover:bg-secondary/30 transition-colors"
            >
              <div className="flex items-center gap-4">
                <div className="w-10 h-10 bg-primary/10 rounded-lg flex items-center justify-center">
                  <FileText size={20} className="text-primary" />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <h4 className="font-medium text-foreground">{doc.name}</h4>
                    {doc.status === "verified" && (
                      <CheckCircle size={14} className="text-success" />
                    )}
                  </div>
                  <div className="flex items-center gap-3 text-sm text-muted-foreground">
                    <span>{doc.type}</span>
                    <span>•</span>
                    <span>{doc.size}</span>
                    <span>•</span>
                    <span>{doc.date}</span>
                  </div>
                </div>
              </div>

              <div className="flex items-center gap-2">
                {!doc.public && (
                  <Badge variant="secondary" className="text-xs">
                    <Lock size={10} className="mr-1" />
                    Investors Only
                  </Badge>
                )}
                <Button variant="ghost" size="sm" disabled>
                  <Eye size={16} className="mr-1" />
                  View
                </Button>
                <Button variant="ghost" size="sm" disabled>
                  <Download size={16} />
                </Button>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Disclaimer */}
      <div className="bg-secondary/50 rounded-xl p-4 text-sm text-muted-foreground">
        <p>
          <strong className="text-foreground">Disclaimer:</strong> These documents are provided for informational purposes only. 
          Please review all materials carefully and consult with your financial advisor before making investment decisions.
        </p>
      </div>
    </div>
  );
};

export default PropertyDocuments;
