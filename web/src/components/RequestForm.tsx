import { useState } from "react";
export function RequestForm({
  onStart,
  busy,
  locked,
}: {
  onStart: (text: string) => Promise<void>;
  busy: boolean;
  locked: boolean;
}) {
  const [text, setText] = useState(
    "Investigate why GreenShop orders fail today",
  );
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        if (text.trim()) void onStart(text.trim());
      }}
    >
      <label htmlFor="request">What needs attention?</label>
      <textarea
        id="request"
        value={text}
        onChange={(event) => setText(event.target.value)}
        minLength={1}
        maxLength={4000}
        rows={5}
        disabled={busy || locked}
        required
      />
      <div className="form-meta">
        <span>English or Russian</span>
        <span>{text.length}/4000</span>
      </div>
      <button
        className="button primary"
        disabled={busy || locked || !text.trim()}
        type="submit"
      >
        {busy
          ? "Starting investigation…"
          : locked
            ? "Investigation in progress"
            : "Start investigation"}
        <span aria-hidden="true">↗</span>
      </button>
      {!locked && (
        <div className="examples">
          <span className="eyebrow">Try a scenario</span>
          <button
            type="button"
            disabled={busy}
            onClick={() =>
              setText("Investigate why GreenShop orders fail today")
            }
          >
            GreenShop · missing orders
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => setText("Check BlueMarket status")}
          >
            BlueMarket · status only
          </button>
        </div>
      )}
    </form>
  );
}
