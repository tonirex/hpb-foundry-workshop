# Lab 1 · Agents & Knowledge — Foundry IQ — portal walkthrough

Main page: [Lab 1](lab-01.md) · [Portal track](PORTAL-TRACK.md)

**35 min.** Retrieval supplies evidence; JSON gives applications predictable fields. Neither alone proves correctness.

1. **Connect:** attach `livewell-guides-kb`, append `knowledge`, and save the supplied JSON Schema.
2. **Run:** send the food prompt, then the supplement prompt in a new chat.
3. **Inspect:** open one retrieved passage and connect it to a claim; explain why the unsupported supplement answer should have no citation.

The [main guide](lab-01.md) has the core instructions and a separate, optional intake-agent setup. Do not change your coach to the intake schema.

<details>
<summary><strong>Click-by-click screenshots and prompts</strong></summary>

1. Open the agent you created in Lab 0.

   **Build → Agents → `livewell-<initials>` → Configure**

   ![Agent configuration page for livewell initials agent](screenshots/lab-01/01-open-agent-configure.png)

2. Start the Foundry IQ connection flow.

   **Knowledge → Add → Connect to Foundry IQ**

   ![Knowledge Add menu with Connect to Foundry IQ selected](screenshots/lab-01/02-knowledge-add-foundry-iq.png)

3. Select the shared workshop knowledge base.

   **Connect to Foundry IQ → Connection `livewell-search` → Knowledge base `livewell-guides-kb` → Connect**

   ![Knowledge panel with livewell-guides-kb selected](screenshots/lab-01/03-connect-foundry-iq.png)

4. Optional: look at the shared knowledge base's settings. Attaching it doesn't show them, and you don't create a knowledge base or index yourself.

   **Build → Knowledge → Knowledge bases → `livewell-guides-kb`** (look only; do not select **Save**, because every participant shares it)

   ![Retrieval reasoning effort, output mode, and retrieval instructions visible](screenshots/lab-01/04-kb-settings-preview.png)

   ⚠️ Foundry IQ portal settings are preview. What each setting does, and why the workshop shares one knowledge base, is in **Explore further** on the [Lab 1](lab-01.md) page.

5. Append the `knowledge` block from [coach-instructions.md](../prompts/coach-instructions.md).

   **Build → Agents → `livewell-<initials>` → Instructions → paste after `base` block → Save**

   ![Instructions with base plus knowledge blocks saved](screenshots/lab-01/05-knowledge-instructions.png)

6. Set the response format to the Lab 1 JSON schema. It is in the **Parameters** panel: select the sliders icon just to the right of the **Model** dropdown.

   **Parameters (icon next to Model) → Text format → JSON Schema → paste all of [`lab1-answer.schema.json`](../config/schemas/lab1-answer.schema.json) in the schema editor and save it → close the panel → Save**

   The panel then shows `livewell_answer` under **Text format**; the pencil icon reopens the editor. Do not pick **JSON Object**: it needs the word "json" in every chat message and otherwise returns a 400 error. The schema also limits `cited_sources` to the real guide ids.

   ![Response format set to JSON schema with livewell_answer pasted](screenshots/lab-01/06-json-response-format.png)

7. Ask the pre-diabetes food question.

   **Chat → New chat → Message box → Send**

   ![JSON answer with cited_sources populated](screenshots/lab-01/07-prediabetes-json-answer.png)

   Prompt `lab1_prediabetes_eat`:

   ```text
   My screening says my glucose is high. What should I eat to manage pre-diabetes?
   ```

8. Open the citation and confirm guide `lg-05-eating-for-pre-diabetes` appears when retrieved.

   **Answer → Citations / Sources → `lg-05-eating-for-pre-diabetes`**

   ![Citation panel showing lg-05 or another allowed LiveWell guide](screenshots/lab-01/08-lg05-citation.png)

9. Open the trace and find the Foundry IQ retrieval span.

   **Response metrics → Traces → Conversation → Foundry IQ / knowledge span**

   ![Trace showing knowledge-base retrieval before the answer](screenshots/lab-01/09-knowledge-trace.png)

10. Ask the supplement question in a new chat.

    **Chat → New chat → Message box → Send**

    ![JSON answer routing to clinician with no cited source](screenshots/lab-01/10-supplement-no-source.png)

    Prompt `lab1_supplement`:

    ```text
    Which supplement should I take to bring my blood sugar down?
    ```

11. Confirm the JSON route and empty citations.

    **Answer JSON → `route` → `cited_sources`**

    ![route clinician and empty cited_sources for the supplement prompt](screenshots/lab-01/11-json-route-clinician.png)

</details>

## What you should see

The food answer returns JSON with `route: "self_care"`, at least one LiveWell guide in `cited_sources`, and practical pre-diabetes advice. The supplement answer returns JSON with `route: "clinician"` and no invented source because the guides do not cover supplement dosing.

## If something looks different

<details>
<summary><strong>Connection and schema troubleshooting</strong></summary>

- ⚠️ If **Knowledge → Add → Connect to Foundry IQ** has moved, search the Add menu for `Foundry IQ`.
- ⚠️ If the KB settings page does not expose retrieval reasoning effort or output mode, capture the available settings and continue.
- If answers include prose outside JSON, recheck **Parameters (icon next to Model) → Text format → JSON Schema** (with `lab1-answer.schema.json` pasted) and the `knowledge` block.
- If the food answer cites no source, confirm `livewell-guides-kb` is attached and Active.

</details>
