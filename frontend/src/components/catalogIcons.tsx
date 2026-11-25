import {
  BatteryCharging,
  Bath,
  Building2,
  Cable,
  CircuitBoard,
  Cog,
  Cylinder,
  Droplet,
  Fan,
  Flame,
  Gauge,
  Hammer,
  Lightbulb,
  type LucideIcon,
  MapPin,
  Plug,
  ShowerHead,
  Snowflake,
  SprayCan,
  Thermometer,
  ToggleRight,
  Truck,
  Waves,
  Wind,
  Wrench,
  Zap,
} from "lucide-react";

// Must match backend/apps/catalog/icons.py (controlled identifiers).
const ICONS: Record<string, LucideIcon> = {
  zap: Zap,
  wrench: Wrench,
  snowflake: Snowflake,
  cable: Cable,
  plug: Plug,
  lightbulb: Lightbulb,
  fan: Fan,
  battery: BatteryCharging,
  toggle: ToggleRight,
  droplet: Droplet,
  shower: ShowerHead,
  waves: Waves,
  cylinder: Cylinder,
  cog: Cog,
  flame: Flame,
  bath: Bath,
  spray: SprayCan,
  gauge: Gauge,
  thermometer: Thermometer,
  circuit_board: CircuitBoard,
  truck: Truck,
  wind: Wind,
  hammer: Hammer,
  map_pin: MapPin,
  building: Building2,
};

/** Icon for a catalog identifier; unknown identifiers fall back to a generic tool. */
export function CatalogIcon({ id, className = "size-8" }: { id: string; className?: string }) {
  const Icon = ICONS[id] ?? Wrench;
  return <Icon className={className} aria-hidden />;
}

export const KNOWN_ICON_IDS = Object.keys(ICONS);
