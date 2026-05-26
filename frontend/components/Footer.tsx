export default function Footer() {
  return (
    <footer className="bg-background border-t border-outline-variant w-full flex justify-between items-center px-margin-mobile md:px-margin-desktop py-unit-2 z-50 shrink-0 font-code-snippet text-code-snippet uppercase">
      <div className="text-primary-fixed-dim font-label-caps text-label-caps">MILLION</div>
      <div className="hidden md:flex gap-unit-4">
        <span className="text-outline hover:text-primary-fixed-dim transition-all cursor-pointer">ST_01</span>
        <span className="text-outline hover:text-primary-fixed-dim transition-all cursor-pointer">ST_02</span>
        <span className="text-outline hover:text-primary-fixed-dim transition-all cursor-pointer">ST_03</span>
      </div>
      <div className="text-primary-fixed-dim font-bold animate-pulse">
        AI: ONLINE // MARKET: LIVE // SYS_REF: 0x71C
      </div>
    </footer>
  );
}
