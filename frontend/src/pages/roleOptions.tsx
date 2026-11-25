import { HardHat, House } from "lucide-react";

import type { Role } from "../api/auth";
import type { TileOption } from "../components/ui/IconTile";
import type { I18nContextValue } from "../i18n/context";

export function roleOptions(t: I18nContextValue["t"]): TileOption<Role>[] {
  return [
    {
      value: "worker",
      label: t("role.worker.title"),
      description: t("role.worker.description"),
      icon: <HardHat className="size-10" aria-hidden />,
    },
    {
      value: "customer",
      label: t("role.customer.title"),
      description: t("role.customer.description"),
      icon: <House className="size-10" aria-hidden />,
    },
  ];
}

export function isRole(value: string | null): value is Role {
  return value === "worker" || value === "customer";
}
