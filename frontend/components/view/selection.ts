// Ce qui est ouvert dans le panneau de détail de « Ce qui tourne ».
export type Tab = "service" | "history" | "card";
export type Selection = { moduleId: number; environmentId: number | null; tab: Tab };
