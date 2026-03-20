export default function LoadingIndicator() {
  return (
    <div className="flex items-center gap-3 pl-11" role="status" aria-label="Loading">
      <div className="bg-surface border border-border rounded-2xl rounded-tl-md px-4 py-3 shadow-sm">
        <div className="flex gap-1.5 items-center">
          {[0, 1, 2].map((i) => (
            <span
              key={i}
              className="h-2 w-2 rounded-full bg-accent-muted"
              style={{
                animation: "typing-dot 1.4s infinite",
                animationDelay: `${i * 0.2}s`,
              }}
            />
          ))}
        </div>
      </div>
    </div>
  );
}
