import "./globals.css";

export const metadata = { title: "Alaap", description: "AI front desk for Indian businesses" };

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
