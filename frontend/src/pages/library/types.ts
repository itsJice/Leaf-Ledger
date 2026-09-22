// Types shared by the product library page and its extracted modules.
// Moved verbatim out of pages/Library.tsx (WP 4.2 library-extract).

export type Product = {
  id: number;
  supplier_sku?: string;
  name: string;
  description?: string;
  category: string;
  unit: string;
  current_price?: number;
  price_updated_at?: string;
  photo_url?: string;
  supplier_id: number;
  supplier_name?: string;
  moq?: number;
  box_qty?: number;
  case_qty?: number;
  availability?: string;
  availability_note?: string;
  upc?: string;
  image_urls?: string[];
  height_in?: number;
  width_in?: number;
  diameter_in?: number;
  length_in?: number;
  weight_lb?: number;
  material?: string;
  finish?: string;
  color?: string;
  style?: string;
  country_of_origin?: string;
  raw_data?: Record<string, any>;
  is_favorited?: boolean;
  is_active?: boolean;
  created_at: string;
  updated_at: string;
};

export type Supplier = { id: number; name: string; website_url?: string; categories?: string[] };
export type ProductPage = {
  items: Product[];
  total: number;
  limit: number;
  offset: number;
};
export type FilterOption = {
  id?: number;
  value: string;
  count?: number;
};
export type LibraryFilterMetadata = {
  generated_at?: string;
  categories?: FilterOption[];
  suppliers?: FilterOption[];
  product_types?: FilterOption[];
  countries?: FilterOption[];
  colors?: FilterOption[];
  availability?: FilterOption[];
};
export type ServerFilterSelection = {
  suppliers: string[];
  categories: string[];
  productTypes: string[];
  colors: string[];
  availability: string[];
};
export type ProjectSummary = {
  id: number;
  name: string;
  client_name?: string;
  container_count?: number;
};
export type ProjectBucket = {
  id: number;
  label?: string;
  sort_order?: number;
};
export type ProjectDetail = {
  id: number;
  name: string;
  client_name?: string;
  containers?: ProjectBucket[];
};
export type ProductSearchEntry = {
  product: Product;
  category: string;
  categoryLabel: string;
  supplierName: string;
  productTypes: string[];
  colors: string[];
  sizes: string[];
  availability?: string;
  country?: string;
  searchText: string;
  codeText: string;
  sortName: string;
  isFavorited: boolean;
};
