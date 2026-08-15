export function VeriGraphLogo() {
  return (
    <svg
      className="brand-logo"
      viewBox="0 0 40 40"
      width="40"
      height="40"
      aria-hidden="true"
    >
      <rect x="1" y="1" width="38" height="38" rx="10" fill="#fbfaf6" />
      <path
        d="M10.5 11.5 20 29l9.5-17.5"
        fill="none"
        stroke="#111827"
        strokeWidth="2.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx="10.5" cy="11.5" r="4" fill="#c8f169" stroke="#111827" strokeWidth="1.75" />
      <circle cx="29.5" cy="11.5" r="4" fill="#ff5a36" stroke="#111827" strokeWidth="1.75" />
      <circle cx="20" cy="29" r="4" fill="#183df0" stroke="#111827" strokeWidth="1.75" />
    </svg>
  );
}
