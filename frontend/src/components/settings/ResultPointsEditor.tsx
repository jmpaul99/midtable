"use client";

import { Input, Label } from "@/components/ui/Field";
import { EditorSection } from "./chrome";
import type { ResultPoints } from "./types";

export function ResultPointsEditor({
  value,
  onChange,
}: {
  value: ResultPoints;
  onChange: (next: ResultPoints) => void;
}) {
  return (
    <EditorSection title="Result points" description="Fantasy points for each match result.">
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
        <Label>
          Win
          <Input
            type="number"
            step="0.5"
            value={value.win}
            onChange={(e) => onChange({ ...value, win: Number(e.target.value) })}
          />
        </Label>
        <Label>
          Draw
          <Input
            type="number"
            step="0.5"
            value={value.draw}
            onChange={(e) => onChange({ ...value, draw: Number(e.target.value) })}
          />
        </Label>
        <Label>
          Loss
          <Input
            type="number"
            step="0.5"
            value={value.loss}
            onChange={(e) => onChange({ ...value, loss: Number(e.target.value) })}
          />
        </Label>
      </div>
    </EditorSection>
  );
}
