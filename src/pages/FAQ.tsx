import { HelpCircle } from "lucide-react";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

const generalFAQs = [
  {
    question: "What is fractional real estate ownership?",
    answer: `Fractional real estate ownership is a structured investment model that allows multiple investors to collectively own a single property.

Key characteristics:
• Each investor owns a legally defined share of the property
• Ownership is documented through investment agreements
• Shares represent proportional economic and financial rights
• All processes are managed digitally through the platform

This model enables lower capital entry, portfolio diversification, professional asset management, and simplified participation in real estate investments.`
  },
  {
    question: "What types of properties are available on the platform?",
    answer: `Capimax PropShare offers a diversified range of real estate assets, including:
• Residential properties
• Commercial properties
• Office buildings
• Hospitality and tourism assets
• Development projects
• Mixed-use properties

Properties are listed across multiple cities and countries to enhance geographic and asset diversification.`
  },
  {
    question: "What is the Income Model?",
    answer: `The Income Model applies to completed, leased, and income-generating properties.

Investors receive:
• Periodic returns (monthly or quarterly)
• Distributions based on actual net rental income
• Returns credited to their platform account
• Option to withdraw or reinvest returns`
  },
  {
    question: "What is the Development Model?",
    answer: `The Development Model focuses on:
• Early-stage investment at lower entry prices
• No periodic income during development
• Capital appreciation upon project completion or sale

This model includes defined development phases, pre-set pricing stages, fixed timelines, and documented development and exit plans.`
  },
  {
    question: "What is the Installment Model?",
    answer: `This model allows investors to acquire a fractional ownership share from the initial offering and pay through structured installment plans without bank interest.

Key features:
• Financial flexibility
• Clear payment schedules
• Right to exit or resell the share
• Transfer of remaining obligations to a new buyer upon resale (subject to approval)`
  },
  {
    question: "Does the platform operate globally?",
    answer: `Yes. Capimax PropShare operates internationally by:
• Establishing a separate SPV for each country or asset
• Complying with local legal and regulatory frameworks
• Preventing cross-border commingling of assets or funds`
  },
  {
    question: "Is the platform legally regulated?",
    answer: `Yes. The platform complies with:
• Local corporate and real estate laws
• Investment and securities regulations (where applicable)
• AML (Anti-Money Laundering) requirements
• KYC (Know Your Customer) procedures`
  },
  {
    question: "Are properties and documents reviewed and verified?",
    answer: `Yes. Every property undergoes:
• Independent professional valuation
• Full legal due diligence
• Verification of ownership, permits, and contracts
• Technical and operational assessment

Only fully approved assets are listed on the platform.`
  },
  {
    question: "Who manages the property and distributes returns?",
    answer: `Property management is handled by licensed property management companies, professional asset managers, and authorized developers (where applicable).

Returns are collected through dedicated asset accounts and distributed proportionally to investors based on documented ownership percentages.`
  }
];

const spvFAQs = [
  {
    question: "What is an SPV?",
    answer: `An SPV (Special Purpose Vehicle) is an independent legal entity established for a single, defined purpose.

Within Capimax PropShare, the SPV:
• Legally owns the real estate asset
• Holds and manages investor ownership rights
• Ensures legal separation between assets

Each listed property is linked to a dedicated SPV, with no mixing of assets or liabilities.`
  },
  {
    question: "What is the role of the SPV within the platform?",
    answer: `The SPV is the legal foundation of the investment structure and is responsible for:
• Holding legal title to the property
• Issuing fractional ownership interests
• Receiving rental income or sale proceeds
• Distributing returns to investors
• Isolating risk between properties
• Maintaining legal continuity regardless of platform operations`
  },
  {
    question: "What happens if the platform shuts down?",
    answer: `If Capimax PropShare ceases operations:
• Investor funds are not lost
• The SPV remains legally active
• The property remains owned by the SPV
• Investor ownership rights remain enforceable

Possible actions include appointment of a new asset manager, continued income distribution, or sale of the asset and distribution of proceeds.`
  },
  {
    question: "Why is the SPV model used instead of direct ownership?",
    answer: `Using an SPV provides:
• Legal separation between platform, investors, and assets
• Easier regulatory compliance
• Risk isolation
• Cross-border investment capability
• Clear tax and legal treatment`
  },
  {
    question: "What are the key advantages of using an SPV?",
    answer: `Key advantages include:
🔒 Strong legal protection
🧱 Asset-level risk isolation
🌍 Global scalability
📑 Clearly defined rights and obligations
🔁 Flexible exit and ownership transfer
⚖️ Auditability and transparency`
  },
  {
    question: "Is there a separate SPV for each property?",
    answer: `Yes. Each property has its own SPV to ensure:
• No commingling of funds
• Independent financial reporting
• Clear profit and cost allocation
• Simplified auditing`
  },
  {
    question: "Is the SPV registered and regulated?",
    answer: `Yes. SPVs are incorporated in suitable jurisdictions and are subject to:
• Corporate laws
• Tax regulations
• Executed investment agreements
• Ongoing legal oversight`
  }
];

const legalFAQs = [
  {
    question: "What is the legal framework of the platform?",
    answer: `The platform operates under:
• Independent SPVs for each asset
• Jurisdiction-specific laws where the property is located
• AML and KYC compliance
• Full legal segregation between platform operations and investor assets`
  },
  {
    question: "Is my investment linked to the platform or the asset?",
    answer: `Your investment is legally linked to the SPV that owns the underlying property.

The platform acts only as a digital and operational facilitator—not an owner or custodian of investor funds.`
  },
  {
    question: "Can the platform control or dispose of my investment?",
    answer: `No. Investor funds are not part of the platform's balance sheet. Assets are owned by the SPV, and any sale or disposal follows predefined legal agreements only.`
  },
  {
    question: "Is the platform responsible for market fluctuations?",
    answer: `No guarantees are provided. However, risk mitigation includes:
• Geographic diversification
• Asset-type diversification
• Independent valuation
• Legal and technical due diligence`
  },
  {
    question: "Can I sell my ownership share?",
    answer: `Yes, subject to platform rules, applicable laws, and approval procedures to ensure compliance and investor protection.`
  },
  {
    question: "What happens if a developer or manager becomes insolvent?",
    answer: `Each party operates under separate contracts. Insolvency does not affect investor ownership. Replacement mechanisms are activated if required, and the asset remains owned by the SPV.`
  },
  {
    question: "How are disputes resolved?",
    answer: `Disputes are resolved through the governing law of the SPV jurisdiction, and arbitration or courts as specified in the agreements.`
  },
  {
    question: "Can investment terms change after subscription?",
    answer: `No. All terms are fixed and legally binding. Any changes apply only to future offerings.`
  },
  {
    question: "Who bears legal liability?",
    answer: `• The SPV bears liability related to the asset
• Investor liability is limited to invested capital
• The platform is responsible only for technology and operations`
  },
  {
    question: "Is the structure valid for international expansion?",
    answer: `Yes. The structure supports:
• Separate SPVs per country
• Compliance with local laws
• No asset commingling
• Transparent reporting`
  }
];

const FAQ = () => {
  return (
    <div className="min-h-screen bg-background">
      {/* Hero Section */}
      <section className="bg-gradient-to-br from-primary/10 via-background to-secondary/10 py-16 md:py-24">
        <div className="container mx-auto px-4">
          <div className="max-w-4xl mx-auto text-center">
            <div className="flex items-center justify-center gap-3 mb-4">
              <HelpCircle className="h-10 w-10 text-primary" />
            </div>
            <h1 className="text-4xl md:text-5xl font-bold text-foreground mb-6">
              Frequently Asked Questions
            </h1>
            <p className="text-xl text-muted-foreground">
              Capimax PropShare is a digitally managed, legally structured fractional real estate ownership platform combining traditional legal protection, SPV-based ownership, and modern digital infrastructure.
            </p>
          </div>
        </div>
      </section>

      <div className="container mx-auto px-4 py-12 max-w-4xl">
        <Tabs defaultValue="general" className="w-full">
          <TabsList className="grid w-full grid-cols-3 mb-8">
            <TabsTrigger value="general">General</TabsTrigger>
            <TabsTrigger value="spv">SPV Structure</TabsTrigger>
            <TabsTrigger value="legal">Legal</TabsTrigger>
          </TabsList>

          <TabsContent value="general">
            <Accordion type="single" collapsible className="w-full">
              {generalFAQs.map((faq, index) => (
                <AccordionItem key={index} value={`general-${index}`}>
                  <AccordionTrigger className="text-left text-foreground hover:no-underline">
                    {faq.question}
                  </AccordionTrigger>
                  <AccordionContent className="text-muted-foreground whitespace-pre-line">
                    {faq.answer}
                  </AccordionContent>
                </AccordionItem>
              ))}
            </Accordion>
          </TabsContent>

          <TabsContent value="spv">
            <Accordion type="single" collapsible className="w-full">
              {spvFAQs.map((faq, index) => (
                <AccordionItem key={index} value={`spv-${index}`}>
                  <AccordionTrigger className="text-left text-foreground hover:no-underline">
                    {faq.question}
                  </AccordionTrigger>
                  <AccordionContent className="text-muted-foreground whitespace-pre-line">
                    {faq.answer}
                  </AccordionContent>
                </AccordionItem>
              ))}
            </Accordion>
          </TabsContent>

          <TabsContent value="legal">
            <Accordion type="single" collapsible className="w-full">
              {legalFAQs.map((faq, index) => (
                <AccordionItem key={index} value={`legal-${index}`}>
                  <AccordionTrigger className="text-left text-foreground hover:no-underline">
                    {faq.question}
                  </AccordionTrigger>
                  <AccordionContent className="text-muted-foreground whitespace-pre-line">
                    {faq.answer}
                  </AccordionContent>
                </AccordionItem>
              ))}
            </Accordion>
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
};

export default FAQ;
