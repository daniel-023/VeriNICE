import Image from "next/image";

export function VeriNICELogo() {
  return (
    <Image
      className="brand-logo"
      src="/verinice-mark-transparent.png"
      width={691}
      height={539}
      alt=""
      priority
      unoptimized
      aria-hidden="true"
    />
  );
}
