import React, { useState } from "react";
import { TextInput, View } from "react-native";
import { useTranslation } from "react-i18next";
import { Button, DateField, Txt, styles as ui } from "@/components/ui";
import { space, useTheme } from "@/lib/theme";
import { fmt, inToMm, type UnitSystem } from "@/lib/units";

/** Lets the farmer report their last irrigation; the water balance then uses it instead of assuming the model schedule. */
export function IrrigationLog({
  date,
  mm,
  today,
  system,
  onSave,
}: {
  date?: string | null;
  mm?: number | null;
  today: string;
  system: UnitSystem;
  onSave: (date: string | null, mm: number | null) => void;
}) {
  const t = useTheme();
  const { t: tr } = useTranslation();
  const [open, setOpen] = useState(false);
  const [d, setD] = useState(date ?? today);
  const [amount, setAmount] = useState("");
  const unit = system === "imperial" ? "in" : "mm";

  if (!open) {
    return (
      <View style={{ marginTop: space.sm, gap: space.xs }}>
        {date && mm ? (
          <Txt v="small" muted testID="irrigation-logged">
            {tr("irrigationLog.logged", { amount: fmt(mm, "mm", system), date })}
          </Txt>
        ) : (
          <Txt v="small" muted>
            {tr("irrigationLog.hint")}
          </Txt>
        )}
        <View style={{ flexDirection: "row", gap: space.sm, flexWrap: "wrap" }}>
          <Button kind="secondary" icon="water" label={tr("irrigationLog.open")} onPress={() => setOpen(true)} testID="irrigation-log-open" />
          {date && mm ? <Button kind="ghost" label={tr("irrigationLog.clear")} onPress={() => onSave(null, null)} /> : null}
        </View>
      </View>
    );
  }
  const value = parseFloat(amount.replace(",", "."));
  const valid = Number.isFinite(value) && value > 0 && value < (unit === "in" ? 20 : 500) && /^\d{4}-\d{2}-\d{2}$/.test(d) && d <= today;
  return (
    <View style={{ marginTop: space.sm }} testID="irrigation-log-form">
      <DateField label={tr("irrigationLog.date")} value={d} onChange={setD} />
      <Txt v="label" style={{ marginBottom: space.xs }}>
        {tr("irrigationLog.amount", { unit })}
      </Txt>
      <TextInput
        accessibilityLabel={tr("irrigationLog.amount", { unit })}
        keyboardType="decimal-pad"
        value={amount}
        onChangeText={setAmount}
        placeholder={unit === "in" ? "1.5" : "40"}
        placeholderTextColor={t.textMuted}
        style={[ui.input, { color: t.text, borderColor: t.border, backgroundColor: t.card }]}
        testID="irrigation-amount"
      />
      <View style={{ flexDirection: "row", gap: space.sm, marginTop: space.sm }}>
        <Button
          label={tr("common.save")}
          disabled={!valid}
          onPress={() => {
            onSave(d, Math.round(unit === "in" ? inToMm(value) : value));
            setOpen(false);
          }}
          testID="irrigation-save"
        />
        <Button kind="ghost" label={tr("common.close")} onPress={() => setOpen(false)} />
      </View>
    </View>
  );
}
