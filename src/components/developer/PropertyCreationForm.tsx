import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Card, CardContent } from "@/components/ui/card";
import { Upload, X, Plus, Loader2, ImageIcon } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@/contexts/AuthContext";
import { propertyApi, ApiError } from "@/lib/api";
import { toast } from "sonner";

interface PropertyFormData {
  title: string;
  description: string;
  location: string;
  property_type: string;
  total_value: string;
  unit_price: string;
  total_units: string;
  minimum_investment: string;
  target_yield: string;
  expected_completion: string;
  spv_name: string;
  spv_registration: string;
  legal_structure: string;
}

const initialFormData: PropertyFormData = {
  title: "",
  description: "",
  location: "",
  property_type: "",
  total_value: "",
  unit_price: "",
  total_units: "100",
  minimum_investment: "500",
  target_yield: "",
  expected_completion: "",
  spv_name: "",
  spv_registration: "",
  legal_structure: "",
};

const propertyTypes = [
  "Residential",
  "Commercial",
  "Mixed-Use",
  "Industrial",
  "Retail",
  "Office",
  "Hotel",
  "Land",
];

export function PropertyCreationForm() {
  const [open, setOpen] = useState(false);
  const [formData, setFormData] = useState<PropertyFormData>(initialFormData);
  const [images, setImages] = useState<File[]>([]);
  const [imagePreview, setImagePreview] = useState<string[]>([]);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const { isAuthenticated } = useAuth();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const handleInputChange = (
    e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>
  ) => {
    const { name, value } = e.target;
    setFormData((prev) => ({ ...prev, [name]: value }));
  };

  const handleSelectChange = (name: string, value: string) => {
    setFormData((prev) => ({ ...prev, [name]: value }));
  };

  const handleImageUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files) return;

    const newImages: File[] = [];
    const newPreviews: string[] = [];

    Array.from(files).forEach((file) => {
      if (file.type.startsWith("image/")) {
        newImages.push(file);
        newPreviews.push(URL.createObjectURL(file));
      }
    });

    setImages((prev) => [...prev, ...newImages]);
    setImagePreview((prev) => [...prev, ...newPreviews]);
  };

  const removeImage = (index: number) => {
    URL.revokeObjectURL(imagePreview[index]);
    setImages((prev) => prev.filter((_, i) => i !== index));
    setImagePreview((prev) => prev.filter((_, i) => i !== index));
  };

  // Create the listing as a draft and submit it for admin review in one step.
  // Image upload rides the app-storage seam (not yet provisioned), so selected
  // files are noted honestly rather than silently dropped; URLs can be added once
  // storage is live.
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!isAuthenticated) {
      toast.error("Please sign in to create a property");
      return;
    }

    setIsSubmitting(true);
    try {
      const created = await propertyApi.create({
        title: formData.title,
        property_type: formData.property_type,
        location: formData.location,
        description: formData.description || undefined,
        total_value: Number(formData.total_value),
        unit_price: Number(formData.unit_price),
        total_units: formData.total_units ? Number(formData.total_units) : undefined,
        minimum_investment: formData.minimum_investment
          ? Number(formData.minimum_investment)
          : undefined,
        target_yield: formData.target_yield ? Number(formData.target_yield) : null,
        expected_completion: formData.expected_completion || null,
        spv_name: formData.spv_name || null,
        spv_registration: formData.spv_registration || null,
        legal_structure: formData.legal_structure || null,
      });
      await propertyApi.submit(created.id);
      toast.success("Property submitted for review", {
        description: images.length
          ? "Image upload will be enabled once app storage is connected."
          : "An admin will review and publish it to the marketplace.",
      });
      await queryClient.invalidateQueries({ queryKey: ["owner-properties"] });
      setOpen(false);
      resetForm();
    } catch (err) {
      const message =
        err instanceof ApiError ? err.message : "Could not create the property. Please try again.";
      toast.error(message);
    } finally {
      setIsSubmitting(false);
    }
  };

  const resetForm = () => {
    setFormData(initialFormData);
    imagePreview.forEach((url) => URL.revokeObjectURL(url));
    setImages([]);
    setImagePreview([]);
  };

  return (
    <Dialog open={open} onOpenChange={(isOpen) => {
      setOpen(isOpen);
      if (!isOpen) resetForm();
    }}>
      <DialogTrigger asChild>
        <Button className="gap-2">
          <Plus className="h-4 w-4" />
          New Project
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Create New Property Listing</DialogTitle>
          <DialogDescription>
            Fill in the details below to list a new property for investment.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-6 mt-4">
          {/* Basic Information */}
          <div className="space-y-4">
            <h3 className="font-semibold text-foreground">Basic Information</h3>
            
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="title">Property Title *</Label>
                <Input
                  id="title"
                  name="title"
                  value={formData.title}
                  onChange={handleInputChange}
                  placeholder="e.g., Creek Harbour Tower"
                  required
                />
              </div>
              
              <div className="space-y-2">
                <Label htmlFor="property_type">Property Type *</Label>
                <Select
                  value={formData.property_type}
                  onValueChange={(value) => handleSelectChange("property_type", value)}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Select type" />
                  </SelectTrigger>
                  <SelectContent>
                    {propertyTypes.map((type) => (
                      <SelectItem key={type} value={type.toLowerCase()}>
                        {type}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="space-y-2">
              <Label htmlFor="location">Location *</Label>
              <Input
                id="location"
                name="location"
                value={formData.location}
                onChange={handleInputChange}
                placeholder="e.g., Dubai Creek Harbour, UAE"
                required
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="description">Description</Label>
              <Textarea
                id="description"
                name="description"
                value={formData.description}
                onChange={handleInputChange}
                placeholder="Describe the property, its features, and investment opportunity..."
                rows={4}
              />
            </div>
          </div>

          {/* Financial Information */}
          <div className="space-y-4">
            <h3 className="font-semibold text-foreground">Financial Details</h3>
            
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="total_value">Total Property Value (USD) *</Label>
                <Input
                  id="total_value"
                  name="total_value"
                  type="number"
                  value={formData.total_value}
                  onChange={handleInputChange}
                  placeholder="e.g., 10000000"
                  required
                />
              </div>
              
              <div className="space-y-2">
                <Label htmlFor="unit_price">Price Per Unit (USD) *</Label>
                <Input
                  id="unit_price"
                  name="unit_price"
                  type="number"
                  value={formData.unit_price}
                  onChange={handleInputChange}
                  placeholder="e.g., 100000"
                  required
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="total_units">Total Units</Label>
                <Input
                  id="total_units"
                  name="total_units"
                  type="number"
                  value={formData.total_units}
                  onChange={handleInputChange}
                  placeholder="100"
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="minimum_investment">Minimum Investment (USD)</Label>
                <Input
                  id="minimum_investment"
                  name="minimum_investment"
                  type="number"
                  value={formData.minimum_investment}
                  onChange={handleInputChange}
                  placeholder="500"
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="target_yield">Target Yield (%)</Label>
                <Input
                  id="target_yield"
                  name="target_yield"
                  type="number"
                  step="0.1"
                  value={formData.target_yield}
                  onChange={handleInputChange}
                  placeholder="e.g., 8.5"
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="expected_completion">Expected Completion</Label>
                <Input
                  id="expected_completion"
                  name="expected_completion"
                  type="date"
                  value={formData.expected_completion}
                  onChange={handleInputChange}
                />
              </div>
            </div>
          </div>

          {/* Legal Information */}
          <div className="space-y-4">
            <h3 className="font-semibold text-foreground">Legal Structure (Optional)</h3>
            
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="space-y-2">
                <Label htmlFor="spv_name">SPV Name</Label>
                <Input
                  id="spv_name"
                  name="spv_name"
                  value={formData.spv_name}
                  onChange={handleInputChange}
                  placeholder="e.g., Creek Tower SPV Ltd"
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="spv_registration">Registration Number</Label>
                <Input
                  id="spv_registration"
                  name="spv_registration"
                  value={formData.spv_registration}
                  onChange={handleInputChange}
                  placeholder="e.g., SPV-2024-001"
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="legal_structure">Legal Structure</Label>
                <Select
                  value={formData.legal_structure}
                  onValueChange={(value) => handleSelectChange("legal_structure", value)}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Select structure" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="spv">Special Purpose Vehicle (SPV)</SelectItem>
                    <SelectItem value="reit">Real Estate Investment Trust</SelectItem>
                    <SelectItem value="llc">Limited Liability Company</SelectItem>
                    <SelectItem value="partnership">Limited Partnership</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
          </div>

          {/* Image Upload */}
          <div className="space-y-4">
            <h3 className="font-semibold text-foreground">Property Images</h3>
            
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              {imagePreview.map((preview, index) => (
                <Card key={index} className="relative overflow-hidden aspect-square">
                  <img
                    src={preview}
                    alt={`Property image ${index + 1}`}
                    className="w-full h-full object-cover"
                  />
                  <Button
                    type="button"
                    variant="destructive"
                    size="icon"
                    className="absolute top-2 right-2 h-6 w-6"
                    onClick={() => removeImage(index)}
                  >
                    <X className="h-4 w-4" />
                  </Button>
                </Card>
              ))}
              
              <label className="cursor-pointer">
                <Card className="aspect-square flex items-center justify-center border-dashed border-2 hover:border-primary hover:bg-primary/5 transition-colors">
                  <CardContent className="flex flex-col items-center justify-center p-4 text-center">
                    <ImageIcon className="h-8 w-8 text-muted-foreground mb-2" />
                    <span className="text-sm text-muted-foreground">Add Image</span>
                  </CardContent>
                </Card>
                <input
                  type="file"
                  accept="image/*"
                  multiple
                  className="hidden"
                  onChange={handleImageUpload}
                />
              </label>
            </div>
          </div>

          {/* Submit Actions */}
          <div className="flex justify-end gap-3 pt-4 border-t">
            <Button
              type="button"
              variant="outline"
              onClick={() => setOpen(false)}
              disabled={isSubmitting}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={isSubmitting}>
              {isSubmitting ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  {uploadProgress > 0 ? `Uploading ${uploadProgress}%` : "Creating..."}
                </>
              ) : (
                <>
                  <Upload className="h-4 w-4 mr-2" />
                  Create Property
                </>
              )}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
