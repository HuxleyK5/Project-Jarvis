export default function AssistantCore({ online }: { online: boolean }) {
  return (
    <div className={`assistant-core ${online ? 'core-online' : ''}`} aria-label="Animated JARVIS visualization, decorative">
      <div className="orbit orbit-outer" />
      <div className="orbit orbit-ticks" />
      <div className="orbit orbit-segments" />
      <div className="orbit orbit-inner" />
      <div className="core-glow" />
      <svg className="core-mark" viewBox="0 0 100 100" aria-hidden="true">
        <path d="M50 12 83 31v38L50 88 17 69V31Z" />
        <path d="M50 24 72 37v26L50 76 28 63V37Z M50 35 63 43v14L50 65 37 57V43Z" />
        <path d="M50 12v23 M83 31 63 43 M83 69 63 57 M50 88V65 M17 69 37 57 M17 31 37 43" />
      </svg>
      <span className="core-cross cross-top" /><span className="core-cross cross-bottom" />
      <span className="core-cross cross-left" /><span className="core-cross cross-right" />
    </div>
  );
}
