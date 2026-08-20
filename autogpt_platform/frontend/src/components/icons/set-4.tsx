import * as React from "react";
import { createIcon } from "@/components/icons/create-icon";

export const IconMedium = createIcon((props) => (
  <svg
    role="img"
    viewBox="0 0 24 24"
    xmlns="http://www.w3.org/2000/svg"
    aria-label="Medium Icon"
    {...props}
  >
    <title>Medium</title>
    <path d="M13.54 12a6.8 6.8 0 01-6.77 6.82A6.8 6.8 0 010 12a6.8 6.8 0 016.77-6.82A6.8 6.8 0 0113.54 12zM20.96 12c0 3.54-1.51 6.42-3.38 6.42-1.87 0-3.39-2.88-3.39-6.42s1.52-6.42 3.39-6.42 3.38 2.88 3.38 6.42M24 12c0 3.17-.53 5.75-1.19 5.75-.66 0-1.19-2.58-1.19-5.75s.53-5.75 1.19-5.75C23.47 6.25 24 8.83 24 12z" />
  </svg>
));

/**
 * YouTube icon component.
 *
 * @component IconYoutube
 * @param {IconProps} props - The props object containing additional attributes and event handlers for the icon.
 * @returns {JSX.Element} - The YouTube icon.
 */
export const IconYoutube = createIcon((props) => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    width="24"
    height="24"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    className="lucide lucide-youtube"
    aria-label="YouTube Icon"
    {...props}
  >
    <title>YouTube</title>
    <path d="M2.5 17a24.12 24.12 0 0 1 0-10 2 2 0 0 1 1.4-1.4 49.56 49.56 0 0 1 16.2 0A2 2 0 0 1 21.5 7a24.12 24.12 0 0 1 0 10 2 2 0 0 1-1.4 1.4 49.55 49.55 0 0 1-16.2 0A2 2 0 0 1 2.5 17" />
    <path d="m10 15 5-3-5-3z" />
  </svg>
));

/**
 * TikTok icon component.
 *
 * @component IconTiktok
 * @param {IconProps} props - The props object containing additional attributes and event handlers for the icon.
 * @returns {JSX.Element} - The TikTok icon.
 */
export const IconTiktok = createIcon((props) => (
  <svg
    role="img"
    viewBox="0 0 24 24"
    xmlns="http://www.w3.org/2000/svg"
    aria-label="TikTok Icon"
    {...props}
  >
    <title>TikTok</title>
    <path d="M12.525.02c1.31-.02 2.61-.01 3.91-.02.08 1.53.63 3.09 1.75 4.17 1.12 1.11 2.7 1.62 4.24 1.79v4.03c-1.44-.05-2.89-.35-4.2-.97-.57-.26-1.1-.59-1.62-.93-.01 2.92.01 5.84-.02 8.75-.08 1.4-.54 2.79-1.35 3.94-1.31 1.92-3.58 3.17-5.91 3.21-1.43.08-2.86-.31-4.08-1.03-2.02-1.19-3.44-3.37-3.65-5.71-.02-.5-.03-1-.01-1.49.18-1.9 1.12-3.72 2.58-4.96 1.66-1.44 3.98-2.13 6.15-1.72.02 1.48-.04 2.96-.04 4.44-.99-.32-2.15-.23-3.02.37-.63.41-1.11 1.04-1.36 1.75-.21.51-.15 1.07-.14 1.61.24 1.64 1.82 3.02 3.5 2.87 1.12-.01 2.19-.66 2.77-1.61.19-.33.4-.67.41-1.06.1-1.79.06-3.57.07-5.36.01-4.03-.01-8.05.02-12.07z" />
  </svg>
));

/**
 * Cross (X) icon component.
 *
 * @component IconCross
 * @param {IconProps} props - The props object containing additional attributes and event handlers for the icon.
 * @returns {JSX.Element} - The cross icon.
 *
 * @example
 * // Default usage
 * <IconCross />
 *
 * @example
 * // With custom color and size
 * <IconCross className="text-primary" size="lg" />
 */
export const IconCross = createIcon((props) => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    viewBox="0 0 14 14"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    aria-label="Close Icon"
    {...props}
  >
    <path d="M1 1L13 13M1 13L13 1" />
  </svg>
));

/**
 * Plus icon component.
 *
 * @component IconPlus
 * @param {IconProps} props - The props object containing additional attributes and event handlers for the icon.
 * @returns {JSX.Element} - The plus icon.
 *
 * @example
 * // Default usage
 * <IconPlus />
 *
 * @example
 * // With custom color and size
 * <IconPlus className="text-primary" size="lg" />
 */
export const IconPlus = createIcon((props) => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    viewBox="0 0 28 28"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    aria-label="Plus Icon"
    {...props}
  >
    <path d="M14 5.83334V22.1667" />
    <path d="M5.83331 14H22.1666" />
  </svg>
));

/**
 * Globe icon component.
 *
 * @component IconGlobe
 * @param {IconProps} props - The props object containing additional attributes and event handlers for the icon.
 * @returns {JSX.Element} - The globe icon.
 */
export const IconGlobe = createIcon((props) => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    width="24"
    height="24"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    className="lucide lucide-globe"
    aria-label="Globe Icon"
    {...props}
  >
    <title>Globe</title>
    <circle cx="12" cy="12" r="10" />
    <path d="M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20" />
    <path d="M2 12h20" />
  </svg>
));

/**
 * Left Arrow icon component.
 *
 * @component IconLeftArrow
 * @param {IconProps} props - The props object containing additional attributes and event handlers for the icon.
 * @returns {JSX.Element} - The left arrow icon.
 */
export const IconLeftArrow = createIcon((props) => (
  <svg
    width="32"
    height="32"
    viewBox="0 0 32 32"
    strokeWidth="2"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    aria-label="Left Arrow Icon"
    {...props}
  >
    <title>Left Arrow</title>
    <path
      d="M20 24L12 16L20 8"
      stroke="currentColor"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
  </svg>
));

/**
 * Right Arrow icon component.
 *
 * @component IconRightArrow
 * @param {IconProps} props - The props object containing additional attributes and event handlers for the icon.
 * @returns {JSX.Element} - The right arrow icon.
 */
export const IconRightArrow = createIcon((props) => (
  <svg
    width="32"
    height="32"
    viewBox="0 0 32 32"
    strokeWidth="2"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    aria-label="Right Arrow Icon"
    {...props}
  >
    <title>Right Arrow</title>
    <path
      d="M12 8L20 16L12 24"
      stroke="currentColor"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
  </svg>
));

/**
 * Person Fill icon component.
 *
 * @component IconPersonFill
 * @param {IconProps} props - The props object containing additional attributes and event handlers for the icon.
 * @returns {JSX.Element} - The person fill icon.
 */
export const IconPersonFill = createIcon((props) => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    viewBox="0 0 53 57"
    fill="currentColor"
    aria-label="Person Fill Icon"
    {...props}
  >
    <title>Person Fill</title>
    <path d="M5.34621 56.5302C3.67955 56.5302 2.36705 56.1552 1.40871 55.4052C0.471214 54.676 0.00246429 53.6656 0.00246429 52.3739C0.00246429 50.3531 0.606631 48.2385 1.81496 46.0302C3.0233 43.801 4.7733 41.7177 7.06496 39.7802C9.35663 37.8218 12.117 36.2385 15.3462 35.0302C18.5962 33.801 22.242 33.1864 26.2837 33.1864C30.3462 33.1864 33.992 33.801 37.2212 35.0302C40.4712 36.2385 43.2316 37.8218 45.5025 39.7802C47.7941 41.7177 49.5441 43.801 50.7525 46.0302C51.9816 48.2385 52.5962 50.3531 52.5962 52.3739C52.5962 53.6656 52.117 54.676 51.1587 55.4052C50.2212 56.1552 48.9191 56.5302 47.2525 56.5302H5.34621ZM26.315 27.5927C24.0858 27.5927 22.0233 26.9885 20.1275 25.7802C18.2316 24.551 16.7004 22.9052 15.5337 20.8427C14.3879 18.7593 13.815 16.426 13.815 13.8427C13.815 11.301 14.3879 9.00932 15.5337 6.96765C16.7004 4.92598 18.2316 3.3114 20.1275 2.1239C22.0233 0.936401 24.0858 0.342651 26.315 0.342651C28.5441 0.342651 30.6066 0.925985 32.5025 2.09265C34.3983 3.25932 35.9191 4.86348 37.065 6.90515C38.2316 8.92598 38.815 11.2177 38.815 13.7802C38.815 16.3843 38.2316 18.7281 37.065 20.8114C35.9191 22.8947 34.3983 24.551 32.5025 25.7802C30.6066 26.9885 28.5441 27.5927 26.315 27.5927Z" />
  </svg>
));

/**
 * Dashboard Layout icon component.
 *
 * @component IconDashboardLayout
 * @param {IconProps} props - The props object containing additional attributes and event handlers for the icon.
 * @returns {JSX.Element} - The dashboard layout icon.
 */
export const IconDashboardLayout = createIcon((props) => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.25"
    strokeLinecap="round"
    strokeLinejoin="round"
    aria-label="Dashboard Layout Icon"
    {...props}
  >
    <path d="M10 3H3V12H10V3Z" />
    <path d="M21 3H14V8H21V3Z" />
    <path d="M21 12H14V21H21V12Z" />
    <path d="M10 16H3V21H10V16Z" />
  </svg>
));

/**
 * Integrations icon component.
 *
 * @component IconIntegrations
 * @param {IconProps} props - The props object containing additional attributes and event handlers for the icon.
 * @returns {JSX.Element} - The integrations icon.
 */
export const IconIntegrations = createIcon((props) => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.25"
    strokeLinecap="round"
    strokeLinejoin="round"
    aria-label="Integrations Icon"
    {...props}
  >
    <path d="M12 20C13.6569 20 15 18.6569 15 17C15 15.3431 13.6569 14 12 14C10.3431 14 9 15.3431 9 17C9 18.6569 10.3431 20 12 20Z" />
    <path d="M4.19937 15.1C3.41858 14.3631 2.81776 13.4565 2.44336 12.4503C2.06896 11.4441 1.93102 10.3653 2.0402 9.29725C2.14939 8.22922 2.50278 7.20061 3.07304 6.29099C3.64329 5.38137 4.41514 4.6151 5.32887 4.05146C6.24261 3.48782 7.27375 3.1419 8.34254 3.04047C9.41133 2.93904 10.4891 3.0848 11.4926 3.46649C12.496 3.84818 13.3983 4.45557 14.1294 5.24168C14.8606 6.02779 15.4012 6.97155 15.7094 7.99997H17.4994C18.4532 8.01283 19.3783 8.32849 20.1411 8.90138C20.9039 9.47427 21.4649 10.2747 21.7431 11.1872C22.0213 12.0997 22.0023 13.077 21.6889 13.978C21.3755 14.879 20.7838 15.6571 19.9994 16.2" />
    <path d="M15.7008 18.4L14.8008 18.1" />
    <path d="M9.20078 15.9L8.30078 15.6" />
    <path d="M10.5996 20.7001L10.8996 19.8" />
    <path d="M13.0996 14.2L13.3996 13.3" />
    <path d="M13.5992 20.7L13.1992 19.7" />
    <path d="M10.8004 14.3L10.4004 13.3" />
    <path d="M8.30078 18.6L9.30078 18.2" />
    <path d="M14.6992 15.8L15.6992 15.4" />
  </svg>
));

/**
 * Profile icon component.
 *
 * @component IconProfile
 * @param {IconProps} props - The props object containing additional attributes and event handlers for the icon.
 * @returns {JSX.Element} - The profile icon.
 */
export const IconProfile = createIcon((props) => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.25"
    strokeLinecap="round"
    strokeLinejoin="round"
    aria-label="Profile Icon"
    {...props}
  >
    <path d="M19 21V19C19 17.9391 18.5786 16.9217 17.8284 16.1716C17.0783 15.4214 16.0609 15 15 15H9C7.93913 15 6.92172 15.4214 6.17157 16.1716C5.42143 16.9217 5 17.9391 5 19V21" />
    <path d="M12 11C14.2091 11 16 9.20914 16 7C16 4.79086 14.2091 3 12 3C9.79086 3 8 4.79086 8 7C8 9.20914 9.79086 11 12 11Z" />
  </svg>
));

/**
 * Sliders icon component.
 *
 * @component IconSliders
 * @param {IconProps} props - The props object containing additional attributes and event handlers for the icon.
 * @returns {JSX.Element} - The sliders icon.
 *
 * @example
 * // Default usage this is the standard usage
 * <IconSliders />
 *
 * @example
 * // With custom color and size these should be used sparingly and only when necessary
 * <IconSliders className="text-primary" size="lg" />
 *
 * @example
 * // With custom size and onClick handler
 * <IconSliders size="sm" onClick={handleOnClick} />
 */
export const IconSliders = createIcon((props) => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.25"
    strokeLinecap="round"
    strokeLinejoin="round"
    aria-label="Sliders Icon"
    {...props}
  >
    <path d="M21 4H14" />
    <path d="M10 4H3" />
    <path d="M21 12H12" />
    <path d="M8 12H3" />
    <path d="M21 20H16" />
    <path d="M12 20H3" />
    <path d="M14 2V6" />
    <path d="M8 10V14" />
    <path d="M16 18V22" />
  </svg>
));

/**
 * More (vertical dots) icon component.
 *
 * @component IconMore
 * @param {IconProps} props - The props object containing additional attributes and event handlers for the icon.
 * @returns {JSX.Element} - The more options icon.
 *
 * @example
 * // Default usage
 * <IconMore />
 *
 * @example
 * // With custom color and size
 * <IconMore className="text-neutral-800" size="lg" />
 */
export const IconMore = createIcon((props) => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    width="20"
    height="20"
    viewBox="0 0 20 20"
    fill="currentColor"
    stroke="currentColor"
    strokeWidth="1.5"
    strokeLinecap="round"
    strokeLinejoin="round"
    aria-label="More Icon"
    {...props}
  >
    <path d="M10 10.8333C10.4603 10.8333 10.8334 10.4602 10.8334 9.99999C10.8334 9.53975 10.4603 9.16666 10 9.16666C9.53978 9.16666 9.16669 9.53975 9.16669 9.99999C9.16669 10.4602 9.53978 10.8333 10 10.8333Z" />
    <path d="M10 4.99999C10.4603 4.99999 10.8334 4.6269 10.8334 4.16666C10.8334 3.70642 10.4603 3.33333 10 3.33333C9.53978 3.33333 9.16669 3.70642 9.16669 4.16666C9.16669 4.6269 9.53978 4.99999 10 4.99999Z" />
    <path d="M10 16.6667C10.4603 16.6667 10.8334 16.2936 10.8334 15.8333C10.8334 15.3731 10.4603 15 10 15C9.53978 15 9.16669 15.3731 9.16669 15.8333C9.16669 16.2936 9.53978 16.6667 10 16.6667Z" />
  </svg>
));

/**
 * External link icon component.
 *
 * @component IconExternalLink
 * @param {IconProps} props - The props object containing additional attributes and event handlers for the icon.
 * @returns {JSX.Element} - The external link icon.
 */
