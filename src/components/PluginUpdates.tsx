import { Field, PanelSection, PanelSectionRow } from "@decky/ui";
import { PLUGIN_UPDATE_URL } from "../utils/constants";
import { SmartClipboardButton } from "./SmartClipboardButton";

export function PluginUpdates() {
  return (
    <PanelSection title="Plugin updates">
      <PanelSectionRow>
        <Field
          label="Latest preview"
          description="Paste this URL into Decky → Settings → Install Plugin from URL. Reuse it whenever you want the newest preview."
        >
          <div style={{ overflowWrap: "anywhere", fontSize: "12px" }}>
            {PLUGIN_UPDATE_URL}
          </div>
        </Field>
      </PanelSectionRow>
      <SmartClipboardButton command={PLUGIN_UPDATE_URL} buttonText="Copy update URL" />
    </PanelSection>
  );
}
