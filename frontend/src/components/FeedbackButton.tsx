"use client";

import { useState } from "react";
import { submitFeedback } from "@/lib/api";

interface FeedbackButtonProps {
  conversationId: string | null;
  messageId: string;
}

export default function FeedbackButton({ conversationId, messageId }: FeedbackButtonProps) {
  const [rating, setRating] = useState<number | null>(null);
  const [submitted, setSubmitted] = useState(false);

  if (!conversationId || submitted) {
    return submitted ? (
      <span className="text-[10px] text-success">✓ Thanks</span>
    ) : null;
  }

  const handleRate = async (value: number) => {
    setRating(value);
    try {
      await submitFeedback(conversationId, messageId, value);
      setSubmitted(true);
    } catch {
      setRating(null);
    }
  };

  return (
    <div className="flex items-center gap-0.5 mt-1">
      {[1, 2, 3, 4, 5].map((v) => (
        <button
          key={v}
          onClick={() => handleRate(v)}
          className={`p-0.5 transition-colors ${
            rating && v <= rating ? "text-accent" : "text-muted hover:text-accent"
          }`}
          title={`Rate ${v}/5`}
        >
          <svg width="12" height="12" viewBox="0 0 24 24" fill={rating && v <= rating ? "currentColor" : "none"} stroke="currentColor" strokeWidth="2">
            <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
          </svg>
        </button>
      ))}
    </div>
  );
}
