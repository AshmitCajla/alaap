import { Plus_Jakarta_Sans } from "next/font/google";
import "./globals.css";

const sans = Plus_Jakarta_Sans({ subsets: ["latin"], variable: "--font-sans", display: "swap" });

export const metadata = {
  title: "Alaap — AI front desk for Indian businesses",
  description: "Alaap answers your shop's calls and WhatsApp in Hindi, Punjabi and English — books, takes orders, follows up.",
};
export const viewport = { width: "device-width", initialScale: 1, themeColor: "#0d7a6f" };

export default function RootLayout({ children }) {
  return (
    <html lang="en" className={sans.variable}>
      <body>{children}</body>
    </html>
  );
}
