import * as React from "react";
import { IconProps } from "@/components/icons/create-icon";
import { IconGlobe, IconYoutube, IconTiktok, IconMedium } from "@/components/icons/set-4";
import { IconFacebook, IconX, IconInstagram, IconLinkedin, IconGithub } from "@/components/icons/set-3";

export enum IconType {
  Marketplace,
  Library,
  Builder,
  Edit,
  LayoutDashboard,
  UploadCloud,
  Settings,
  LogOut,
  AutoGPTLogo,
  Sliders,
  Chat,
}

export function getIconForSocial(
  url: string,
  props: IconProps,
): React.ReactNode {
  let host;
  try {
    host = new URL(url).host;
  } catch {
    return <IconGlobe {...props} />;
  }

  if (host === "facebook.com" || host.endsWith(".facebook.com")) {
    return <IconFacebook {...props} />;
  } else if (host === "twitter.com" || host.endsWith(".twitter.com")) {
    return <IconX {...props} />;
  } else if (host === "x.com" || host.endsWith(".x.com")) {
    return <IconX {...props} />;
  } else if (host === "instagram.com" || host.endsWith(".instagram.com")) {
    return <IconInstagram {...props} />;
  } else if (host === "linkedin.com" || host.endsWith(".linkedin.com")) {
    return <IconLinkedin {...props} />;
  } else if (host === "github.com" || host.endsWith(".github.com")) {
    return <IconGithub {...props} />;
  } else if (host === "youtube.com" || host.endsWith(".youtube.com")) {
    return <IconYoutube {...props} />;
  } else if (host === "tiktok.com" || host.endsWith(".tiktok.com")) {
    return <IconTiktok {...props} />;
  } else if (host === "medium.com" || host.endsWith(".medium.com")) {
    return <IconMedium {...props} />;
  } else {
    return <IconGlobe {...props} />;
  }
}

