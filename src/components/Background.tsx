export default function Background() {
  return (
    <div aria-hidden className="pointer-events-none fixed inset-0 -z-10 overflow-hidden">
      <div className="absolute -top-40 -left-40 h-[38rem] w-[38rem] rounded-full bg-violet-600/30 blur-[120px] animate-float" />
      <div className="absolute top-1/3 -right-48 h-[34rem] w-[34rem] rounded-full bg-cyan-500/20 blur-[120px] animate-float-slow" />
      <div className="absolute -bottom-56 left-1/3 h-[30rem] w-[30rem] rounded-full bg-fuchsia-500/20 blur-[120px] animate-float" />
      <div className="absolute inset-0 grid-bg" />
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,transparent_40%,var(--color-ink-950)_100%)]" />
    </div>
  );
}
