import { useId } from "react";

type Option<T extends string> = { value: T; label: string };

/** Compact single-choice control built on native radios: keyboard and screen-reader behaviour come from the platform. */
export function Segmented<T extends string>({
  value, onChange, options, label,
}: {
  value: T;
  onChange: (v: T) => void;
  options: readonly Option<T>[];
  label: string;
}) {
  const name = useId();
  return (
    <fieldset className="m-0 inline-flex max-w-full min-w-0 flex-wrap rounded-md border p-0.5">
      <legend className="sr-only">{label}</legend>
      {options.map((o) => (
        <label key={o.value} className="relative">
          <input
            type="radio"
            name={name}
            value={o.value}
            checked={o.value === value}
            onChange={() => onChange(o.value)}
            className="peer sr-only"
          />
          <span className="flex min-h-11 min-w-11 cursor-pointer items-center justify-center sm:min-h-0 sm:min-w-0 whitespace-nowrap rounded px-2.5 py-1 text-xs text-muted-foreground peer-checked:bg-muted peer-checked:font-medium peer-checked:text-foreground peer-focus-visible:outline peer-focus-visible:outline-2 peer-focus-visible:outline-offset-1 hover:text-foreground">
            {o.label}
          </span>
        </label>
      ))}
    </fieldset>
  );
}
