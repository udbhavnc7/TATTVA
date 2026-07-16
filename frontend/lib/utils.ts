import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

/**
 * Utility for merging Tailwind class names safely.
 * Used by shadcn/ui components throughout the project.
 */
export function cn(...inputs: ClassValue[]) {
    return twMerge(clsx(inputs));
}
