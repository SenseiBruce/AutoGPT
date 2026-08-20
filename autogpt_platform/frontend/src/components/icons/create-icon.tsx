import * as React from "react";
import { cn } from "@/lib/utils";

/**
 * Represents different variants of an icon, based on its size.
 */
export const iconVariants = {
  size: {
    default: "size-4",
    sm: "size-2",
    lg: "size-6",
  },
} as const;

/**
 * Props for the Icon component.
 */
export interface IconProps extends React.SVGProps<SVGSVGElement> {
  size?: keyof typeof iconVariants.size;
}

/**
 * Creates an icon component that wraps a given SVG icon component.
 */
export const createIcon = <P extends React.SVGProps<SVGSVGElement>>(
  IconComponent: React.FC<P>,
): React.ForwardRefExoticComponent<
  IconProps & React.RefAttributes<SVGSVGElement>
> => {
  const Icon = React.forwardRef<SVGSVGElement, IconProps>(
    ({ className, size = "default", ...props }, ref) => {
      return (
        <IconComponent
          className={cn(iconVariants.size[size], className)}
          ref={ref}
          {...(props as P)}
          aria-label={IconComponent.displayName || "Icon"}
        />
      );
    },
  );
  Icon.displayName = IconComponent.name || "Icon";
  return Icon;
};
