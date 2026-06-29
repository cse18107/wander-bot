export interface Money {
  amount: number;
  currency: string;
}

export interface OptionStat {
  icon: string;
  value: string;
}

export interface CardOption {
  icon: string;
  title: string;
  from_label?: string | null;
  to_label?: string | null;
  stats?: OptionStat[];
  note?: string | null;
}

export interface TransportLeg {
  mode: string;
  icon: string;
  from_place: string;
  to_place: string;
  duration?: string | null;
  cost?: string | null;
}

export interface TransportRoute {
  title: string;
  legs: TransportLeg[];
  total_duration?: string | null;
  total_cost?: string | null;
  note?: string | null;
}

export interface ChatCard {
  kind?: "image" | "options";
  // image card
  label?: string;
  images?: string[];
  price?: number;
  currency?: string;
  note?: string | null;
  // options card
  heading?: string | null;
  options?: CardOption[];
}

export interface FlightSegment {
  carrier: string;
  flight_number: string;
  origin: string;
  destination: string;
  departure_at?: string;
  arrival_at?: string;
  origin_name?: string | null;
  origin_city?: string | null;
  destination_name?: string | null;
  destination_city?: string | null;
  carrier_name?: string | null;
}

export interface Flight {
  id: string;
  price: Money;
  stops: number;
  segments: FlightSegment[];
}

export interface Hotel {
  name: string;
  price: Money;
  bookable?: boolean;
  source?: string | null;
  note?: string | null;
  check_in?: string;
  check_out?: string;
}

export interface Activity {
  name: string;
  price?: Money | null;
}

export interface Selections {
  flight: Flight | null;
  hotel: Hotel | null;
  activities: Activity[];
}

export interface BudgetTier {
  name: string;
  total: number;
  home_total?: number | null;
  note?: string | null;
}

export interface Budget {
  target: number | null;
  currency: string;
  status: "unknown" | "ok" | "over";
  total: number;
  local_total?: number | null;
  local_currency?: string | null;
  home_total?: number | null;
  home_currency?: string | null;
  estimated?: boolean;
  tiers?: BudgetTier[];
  selected_tier?: string | null;
}

export interface ItineraryDay {
  day: number;
  title: string;
  items: string[];
}

export interface Itinerary {
  summary: string;
  headline?: string | null;
  days: ItineraryDay[];
  local_food?: string[];
  occasions?: string[];
  best_known_for?: string | null;
  description?: string | null;
  local_language?: string | null;
  local_currency?: string | null;
}

export interface FlightOption {
  id: string;
  price: Money;
  currency_name?: string | null;
  origin: string;
  destination: string;
  origin_name?: string | null;
  origin_city?: string | null;
  destination_name?: string | null;
  destination_city?: string | null;
  depart: string;
  arrive: string;
  carrier: string;
  carrier_name?: string | null;
  number: string;
  stops: number;
  date?: string | null;
}

export interface DayPlace {
  name: string;
  how_to_reach: string;
  best_vehicle: string;
  image?: string | null;
}
export interface Walkable {
  name: string;
  walk_time_min: number;
}
export interface DayDetail {
  day: number;
  title: string;
  city?: string | null;
  places: DayPlace[];
  weather?: string | null;
  weather_detail?: {
    condition?: string;
    temp_max?: number;
    temp_min?: number;
    precip_mm?: number;
    wind_kmh?: number;
  } | null;
  street_food: (string | { name: string; veg?: boolean })[];
  restaurants: (string | { name: string; diet?: string; link?: string })[];
  walkable: Walkable[];
  images: string[];
}

export interface PlaceDetail {
  name: string;
  city?: string | null;
  description?: string;
  kind?: string | null;
  how_to_reach?: string | null;
  best_time?: string | null;
  highlights?: string[];
  images?: string[];
}

export interface ApprovalPayload {
  type: string;
  total: number;
  flight: string | null;
  hotel: string | null;
}
