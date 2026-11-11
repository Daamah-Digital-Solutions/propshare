import { useEffect, useRef, useState, type ChangeEvent, type FocusEvent, type KeyboardEvent } from "react";

interface Options {
  /** The committed number (what the page computes with). */
  value: number;
  /** Called with a number inside [min, max] while typing, and with the corrected one on leaving. */
  onValueChange: (value: number) => void;
  min: number;
  max: number;
  /** Whole numbers only (units). */
  integer?: boolean;
}

/**
 * A number field the user can clear and retype freely.
 *
 * Correcting the number on every keystroke (clamping to the minimum) makes a field impossible
 * to edit: clearing it puts the minimum straight back, and the next digit lands after it. Here
 * the field keeps what is typed; a number inside [min, max] reaches the page at once, anything
 * else (empty, too small, too large) waits, and on leaving the field (or Enter) it is corrected
 * to the nearest allowed number, or back to the last one when the field was left empty.
 */
export function useNumberDraft({ value, onValueChange, min, max, integer = false }: Options) {
  const [text, setText] = useState(() => String(value));
  const textRef = useRef(text);
  textRef.current = text;

  // The value changed from outside (slider, quick amounts, a prepared order): show it, unless
  // it is the number already typed (then the user's own spelling, such as "150.", stays).
  useEffect(() => {
    if (parse(textRef.current) !== value) setText(String(value));
  }, [value]);

  const inRange = (n: number | null): n is number =>
    n !== null && n >= min && n <= max && (!integer || Number.isInteger(n));
  const invalid = !inRange(parse(text));

  const commit = () => {
    const n = parse(textRef.current);
    let next: number;
    if (n === null) next = value;
    else {
      next = Math.min(Math.max(n, min), max);
      if (integer) next = Math.min(Math.max(Math.round(next), Math.ceil(min)), Math.floor(max));
    }
    setText(String(next));
    if (next !== value) onValueChange(next);
  };

  return {
    invalid,
    inputProps: {
      value: text,
      inputMode: integer ? ("numeric" as const) : ("decimal" as const),
      "aria-invalid": invalid || undefined,
      onChange: (e: ChangeEvent<HTMLInputElement>) => {
        const t = e.target.value;
        setText(t);
        const n = parse(t);
        if (inRange(n) && n !== value) onValueChange(n);
      },
      onBlur: (_e: FocusEvent<HTMLInputElement>) => commit(),
      onKeyDown: (e: KeyboardEvent<HTMLInputElement>) => {
        if (e.key === "Enter") commit();
      },
    },
  };
}

function parse(text: string): number | null {
  const t = text.trim();
  if (t === "") return null;
  const n = Number(t);
  return Number.isFinite(n) ? n : null;
}
