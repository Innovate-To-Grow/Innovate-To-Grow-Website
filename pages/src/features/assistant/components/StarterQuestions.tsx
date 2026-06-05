interface StarterQuestionsProps {
  questions: string[];
  disabled: boolean;
  onSelect: (question: string) => void;
}

/** Tappable chips that submit a pre-written starter question. */
export function StarterQuestions({questions, disabled, onSelect}: StarterQuestionsProps) {
  if (questions.length === 0) return null;
  return (
    <div className="itg-assistant__starters">
      {questions.map((question) => (
        <button
          key={question}
          type="button"
          className="itg-assistant__starter"
          disabled={disabled}
          onClick={() => onSelect(question)}
        >
          {question}
        </button>
      ))}
    </div>
  );
}
