import * as React from "react";
import { createIcon } from "@/components/icons/create-icon";

export const IconUploadCloud = createIcon((props) => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    aria-label="Upload Cloud Icon"
    {...props}
  >
    <path d="M4.00034 14.899C3.25738 14.1399 2.69691 13.2217 2.36137 12.214C2.02584 11.2062 1.92405 10.1353 2.0637 9.08232C2.20335 8.02938 2.5808 7.02202 3.16743 6.13655C3.75407 5.25109 4.53452 4.51074 5.44967 3.97157C6.36482 3.43241 7.39067 3.10857 8.44951 3.0246C9.50835 2.94062 10.5724 3.09871 11.5611 3.48688C12.5498 3.87505 13.4372 4.48313 14.1561 5.26506C14.8749 6.04698 15.4065 6.98225 15.7103 8.00002H17.5003C18.4659 7.99991 19.4058 8.31034 20.1813 8.88546C20.9569 9.46058 21.5269 10.2699 21.8071 11.1938C22.0874 12.1178 22.063 13.1074 21.7377 14.0164C21.4123 14.9254 20.8032 15.7057 20.0003 16.242" />
    <path d="M12 12V21" />
    <path d="M16 16L12 12L8 16" />
  </svg>
));

/**
 * Chevron up icon component.
 *
 * @component IconChevronUp
 * @param {IconProps} props - The props object containing additional attributes and event handlers for the icon.
 * @returns {JSX.Element} - The chevron up icon.
 */
export const IconChevronUp = createIcon((props) => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    aria-label="Chevron Up Icon"
    {...props}
  >
    <path d="M17 14l-5-5-5 5" />
  </svg>
));
/**
 * Marketplace icon component.
 *
 * @component IconMarketplace
 * @param {IconProps} props - The props object containing additional attributes and event handlers for the icon.
 * @returns {JSX.Element} - The marketplace icon.
 */
export const IconMarketplace = createIcon((props) => (
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
    aria-label="Marketplace Icon"
    {...props}
  >
    <title>Marketplace</title>
    <path d="m2 7 4.41-4.41A2 2 0 0 1 7.83 2h8.34a2 2 0 0 1 1.42.59L22 7" />
    <path d="M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8" />
    <path d="M15 22v-4a2 2 0 0 0-2-2h-2a2 2 0 0 0-2 2v4" />
    <path d="M2 7h20" />
    <path d="M22 7v3a2 2 0 0 1-2 2a2.7 2.7 0 0 1-1.59-.63.7.7 0 0 0-.82 0A2.7 2.7 0 0 1 16 12a2.7 2.7 0 0 1-1.59-.63.7.7 0 0 0-.82 0A2.7 2.7 0 0 1 12 12a2.7 2.7 0 0 1-1.59-.63.7.7 0 0 0-.82 0A2.7 2.7 0 0 1 8 12a2.7 2.7 0 0 1-1.59-.63.7.7 0 0 0-.82 0A2.7 2.7 0 0 1 4 12a2 2 0 0 1-2-2V7" />
  </svg>
));

/**
 * Shopping Cart icon component.
 *
 * @component IconShoppingCart
 * @param {IconProps} props - The props object containing additional attributes and event handlers for the icon.
 * @returns {JSX.Element} - The shopping cart icon.
 */
export const IconShoppingCart = createIcon((props) => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    width="25"
    height="24"
    viewBox="0 0 25 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    aria-label="Shopping Cart Icon"
    {...props}
  >
    <title>Shopping Cart</title>
    <path d="M8.8696 22C9.42188 22 9.8696 21.5523 9.8696 21C9.8696 20.4477 9.42188 20 8.8696 20C8.31731 20 7.8696 20.4477 7.8696 21C7.8696 21.5523 8.31731 22 8.8696 22Z" />
    <path d="M19.8696 22C20.4219 22 20.8696 21.5523 20.8696 21C20.8696 20.4477 20.4219 20 19.8696 20C19.3173 20 18.8696 20.4477 18.8696 21C18.8696 21.5523 19.3173 22 19.8696 22Z" />
    <path d="M2.91959 2.04999H4.91959L7.57959 14.47C7.67716 14.9248 7.93026 15.3315 8.2953 15.6198C8.66034 15.9082 9.11449 16.0603 9.57959 16.05H19.3596C19.8148 16.0493 20.2561 15.8933 20.6106 15.6078C20.9652 15.3224 21.2117 14.9245 21.3096 14.48L22.9596 7.04999H5.98959" />
  </svg>
));

/**
 * Laptop icon component.
 *
 * @component IconLaptop
 * @param {IconProps} props - The props object containing additional attributes and event handlers for the icon.
 * @returns {JSX.Element} - The laptop icon.
 */
export const IconLaptop = createIcon((props) => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    width="25"
    height="24"
    viewBox="0 0 25 24"
    fill="none"
    aria-label="Laptop Icon"
    {...props}
  >
    <title>Laptop</title>
    <g id="icon/laptop">
      <path
        id="Vector"
        d="M20.8696 16V7C20.8696 6.46957 20.6589 5.96086 20.2838 5.58579C19.9087 5.21071 19.4 5 18.8696 5H6.8696C6.33917 5 5.83046 5.21071 5.45539 5.58579C5.08032 5.96086 4.8696 6.46957 4.8696 7V16M20.8696 16H4.8696M20.8696 16L22.1496 18.55C22.2267 18.703 22.2632 18.8732 22.2556 19.0444C22.248 19.2155 22.1966 19.3818 22.1062 19.5274C22.0159 19.6729 21.8897 19.7928 21.7397 19.8756C21.5897 19.9584 21.4209 20.0012 21.2496 20H4.4896C4.31829 20.0012 4.14955 19.9584 3.99955 19.8756C3.84955 19.7928 3.72333 19.6729 3.63298 19.5274C3.54264 19.3818 3.4912 19.2155 3.4836 19.0444C3.47601 18.8732 3.51251 18.703 3.5896 18.55L4.8696 16"
      />
    </g>
  </svg>
));

/**
 * Boxes icon component.
 *
 * @component IconBoxes
 * @param {IconProps} props - The props object containing additional attributes and event handlers for the icon.
 * @returns {JSX.Element} - The boxes icon.
 */
export const IconBoxes = createIcon((props) => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    width="25"
    height="24"
    viewBox="0 0 25 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    aria-label="Boxes Icon"
    {...props}
  >
    <title>Boxes</title>
    <path d="M3.8396 12.92C3.54436 13.0974 3.29993 13.348 3.12999 13.6476C2.96005 13.9472 2.87035 14.2856 2.8696 14.63V17.87C2.87035 18.2144 2.96005 18.5528 3.12999 18.8524C3.29993 19.152 3.54436 19.4026 3.8396 19.58L6.8396 21.38C7.15066 21.5669 7.50671 21.6656 7.8696 21.6656C8.23249 21.6656 8.58853 21.5669 8.8996 21.38L12.8696 19V13.5L7.8696 10.5L3.8396 12.92Z" />
    <path d="M7.8696 16.5L3.1296 13.65" />
    <path d="M7.8696 16.5L12.8696 13.5" />
    <path d="M7.8696 16.5V21.67" />
    <path d="M12.8696 13.5V19L16.8396 21.38C17.1507 21.5669 17.5067 21.6656 17.8696 21.6656C18.2325 21.6656 18.5885 21.5669 18.8996 21.38L21.8996 19.58C22.1948 19.4026 22.4393 19.152 22.6092 18.8524C22.7792 18.5528 22.8688 18.2144 22.8696 17.87V14.63C22.8688 14.2856 22.7792 13.9472 22.6092 13.6476C22.4393 13.348 22.1948 13.0974 21.8996 12.92L17.8696 10.5L12.8696 13.5Z" />
    <path d="M17.8696 16.5L12.8696 13.5" />
    <path d="M17.8696 16.5L22.6096 13.65" />
    <path d="M17.8696 16.5V21.67" />
    <path d="M8.8396 4.41997C8.54436 4.59735 8.29993 4.84797 8.12999 5.14756C7.96005 5.44714 7.87035 5.78554 7.8696 6.12997V10.5L12.8696 13.5L17.8696 10.5V6.12997C17.8688 5.78554 17.7792 5.44714 17.6092 5.14756C17.4393 4.84797 17.1948 4.59735 16.8996 4.41997L13.8996 2.61997C13.5885 2.43308 13.2325 2.33435 12.8696 2.33435C12.5067 2.33435 12.1507 2.43308 11.8396 2.61997L8.8396 4.41997Z" />
    <path d="M12.8696 8.00002L8.1296 5.15002" />
    <path d="M12.8696 8.00002L17.6096 5.15002" />
    <path d="M12.8696 13.5V8" />
  </svg>
));

/**
 * Library icon component.
 *
 * @component IconLibrary
 * @param {IconProps} props - The props object containing additional attributes and event handlers for the icon.
 * @returns {JSX.Element} - The library icon.
 */
export const IconLibrary = createIcon((props) => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    aria-label="Library Icon"
    {...props}
  >
    <title>Library</title>
    <path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H19a1 1 0 0 1 1 1v18a1 1 0 0 1-1 1H6.5a1 1 0 0 1 0-5H20" />
  </svg>
));

export const IconStar = createIcon((props) => (
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
    aria-label="Star Icon"
    {...props}
  >
    <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
  </svg>
));

export const IconStarFilled = createIcon((props) => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    width="24"
    height="24"
    viewBox="0 0 24 24"
    fill="currentColor"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    aria-label="Star Filled Icon"
    {...props}
  >
    <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
  </svg>
));

/**
 * Generates an array of JSX elements representing star icons based on the average rating.
 *
 * @param avgRating - The average rating (0 to 5)
 * @returns An array of star icons as JSX elements
 */
export function StarRatingIcons(avgRating: number): JSX.Element[] {
  const stars: JSX.Element[] = [];
  const rating = Math.max(0, Math.min(5, avgRating));
  for (let i = 1; i <= 5; i++) {
    if (i <= rating) {
      stars.push(
        <IconStarFilled key={i} className="text-black dark:text-yellow-500" />,
      );
    } else {
      stars.push(
        <IconStar key={i} className="text-black dark:text-yellow-500" />,
      );
    }
  }
  return stars;
}

/**
 * GitHub icon component.
 *
 * @component IconGithub
 * @param {IconProps} props - The props object containing additional attributes and event handlers for the icon.
 * @returns {JSX.Element} - The GitHub icon.
 */
export const IconGithub = createIcon((props) => (
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
    aria-label="GitHub Icon"
    {...props}
  >
    <title>GitHub</title>
    <path d="M15 22v-4a4.8 4.8 0 0 0-1-3.5c3 0 6-2 6-5.5.08-1.25-.27-2.48-1-3.5.28-1.15.28-2.35 0-3.5 0 0-1 0-3 1.5-2.64-.5-5.36-.5-8 0C6 2 5 2 5 2c-.3 1.15-.3 2.35 0 3.5A5.403 5.403 0 0 0 4 9c0 3.5 3 5.5 6 5.5-.39.49-.68 1.05-.85 1.65-.17.6-.22 1.23-.15 1.85v4" />
    <path d="M9 18c-4.51 2-5-2-7-2" />
  </svg>
));

/**
 * LinkedIn icon component.
 *
 * @component IconLinkedin
 * @param {IconProps} props - The props object containing additional attributes and event handlers for the icon.
 * @returns {JSX.Element} - The LinkedIn icon.
 */
export const IconLinkedin = createIcon((props) => (
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
    aria-label="LinkedIn Icon"
    {...props}
  >
    <title>LinkedIn</title>
    <path d="M16 8a6 6 0 0 1 6 6v7h-4v-7a2 2 0 0 0-2-2 2 2 0 0 0-2 2v7h-4v-7a6 6 0 0 1 6-6z" />
    <rect width="4" height="12" x="2" y="9" />
    <circle cx="4" cy="4" r="2" />
  </svg>
));

/**
 * Facebook icon component.
 *
 * @component IconFacebook
 * @param {IconProps} props - The props object containing additional attributes and event handlers for the icon.
 * @returns {JSX.Element} - The Facebook icon.
 */
export const IconFacebook = createIcon((props) => (
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
    aria-label="Facebook Icon"
    {...props}
  >
    <title>Facebook</title>
    <path d="M18 2h-3a5 5 0 0 0-5 5v3H7v4h3v8h4v-8h3l1-4h-4V7a1 1 0 0 1 1-1h3z" />
  </svg>
));

/**
 * Instagram icon component.
 *
 * @component IconInstagram
 * @param {IconProps} props - The props object containing additional attributes and event handlers for the icon.
 * @returns {JSX.Element} - The Instagram icon.
 */
export const IconInstagram = createIcon((props) => (
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
    aria-label="Instagram Icon"
    {...props}
  >
    <title>Instagram</title>
    <rect width="20" height="20" x="2" y="2" rx="5" ry="5" />
    <path d="M16 11.37A4 4 0 1 1 12.63 8 4 4 0 0 1 16 11.37z" />
    <line x1="17.5" x2="17.51" y1="6.5" y2="6.5" />
  </svg>
));

/**
 * X (Twitter) icon component.
 *
 * @component IconX
 * @param {IconProps} props - The props object containing additional attributes and event handlers for the icon.
 * @returns {JSX.Element} - The X (Twitter) icon.
 */
export const IconX = createIcon((props) => (
  <svg
    role="img"
    viewBox="0 0 24 24"
    xmlns="http://www.w3.org/2000/svg"
    aria-label="X (Twitter) Icon"
    {...props}
  >
    <title>X (Twitter)</title>
    <path d="M18.901 1.153h3.68l-8.04 9.19L24 22.846h-7.406l-5.8-7.584-6.638 7.584H.474l8.6-9.83L0 1.154h7.594l5.243 6.932ZM17.61 20.644h2.039L6.486 3.24H4.298Z" />
  </svg>
));

/**
 * Medium icon component.
 *
 * @component IconMedium
 * @param {IconProps} props - The props object containing additional attributes and event handlers for the icon.
 * @returns {JSX.Element} - The Medium icon.
 */
