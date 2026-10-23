"""Human annotation with optional explicitly model-informed pilot error review."""

from pathlib import Path

import streamlit as st

from amc.youtube.annotation import disagreements, load_sheet, save_label
from amc.youtube.validation import read

ROOT = Path(__file__).resolve().parents[2]
DIRECTORY = ROOT / "data/youtube/labeling"
RELEVANCE = {"Related": "relevant", "Unrelated": "unrelated", "Unclear": "unclear"}
IMPACT = {
    "Positive": "positive",
    "Negative": "negative",
    "Mixed": "mixed",
    "Neutral": "neutral",
    "Unclear": "unclear",
}


def render() -> None:
    """Show one frozen sample and save explicit human decisions."""
    st.title("Label comments")
    st.caption("Human annotation · no AI suggestions · save and continue")
    available = [
        name
        for name in (
            "pilot_annotator_a.csv",
            "pilot_annotator_b.csv",
            "evaluation_annotator_a.csv",
            "evaluation_annotator_b.csv",
        )
        if (DIRECTORY / name).is_file()
    ]
    if not available:
        st.info("Prepare the annotation sheets first: make youtube-labeling")
        return
    sheet = st.selectbox("Your sheet", available)
    if sheet.startswith("evaluation"):
        st.warning("Held-out evaluation: use only after the pilot rules and model are frozen.")
    st.caption(
        "A and B should work independently on separate sheets. Do not inspect each other's labels."
    )
    path = DIRECTORY / sheet
    try:
        rows, digest = load_sheet(path)
    except (OSError, ValueError, KeyError, TypeError) as error:
        st.error(f"Cannot load sheet: {error}")
        return
    completed = sum(bool(row["relevance"] and row["impact"]) for row in rows)
    st.progress(completed / len(rows), text=f"Saved: {completed} / {len(rows)}")
    review = st.checkbox(
        "Only disagreements with Ollama (pilot review)", disabled=sheet.startswith("evaluation")
    )
    indices = list(range(len(rows)))
    cohort = None
    if review:
        st.warning(
            "Model-informed pilot review, not independent validation. AI labels stay hidden."
        )
        try:
            predictions = DIRECTORY.parent / "yt_comments_classified.csv"
            cohorts = sorted(
                {
                    (r["model"], r["prompt_hash"])
                    for r in read(predictions, ("model", "prompt_hash"))
                }
            )
            cohort = st.selectbox(
                "Prediction run", cohorts, format_func=lambda x: f"{x[0]} · {x[1][:12]}"
            )
            if cohort is None:
                st.info("No model predictions available.")
                return
            indices = disagreements(rows, DIRECTORY / "sample_key.csv", predictions, cohort)
        except (OSError, ValueError, KeyError) as error:
            st.error(f"Cannot compare: {error}")
            return
        st.caption(
            f"Comments with disagreements: {len(indices)}. Keep your label if it is justified."
        )
        if not indices:
            st.success("No disagreements remain among completed labels.")
            return
    position_key = f"position:{sheet}:{review}:{cohort}"
    if position_key not in st.session_state:
        st.session_state[position_key] = next(
            (i for i in indices if not rows[i]["relevance"]), indices[0]
        )
    if st.session_state[position_key] not in indices:
        st.session_state[position_key] = indices[0]
    index = st.session_state[position_key]
    page_index = indices.index(index)
    row = rows[index]
    previous, middle, following = st.columns([1, 2, 1])
    if previous.button("← Previous", disabled=page_index == 0):
        st.session_state[position_key] = indices[page_index - 1]
        st.rerun()
    middle.write(f"Comment {page_index + 1} / {len(indices)} · {row['sample_id']}")
    if following.button("Skip →", disabled=page_index == len(indices) - 1):
        st.session_state[position_key] = indices[page_index + 1]
        st.rerun()
    st.text(row["text_clean"])
    widget_key = f"{sheet}:{row['sample_id']}"
    rel_values = list(RELEVANCE.values())
    rel_choice = st.radio(
        "1. Does it discuss AI's impact on work, employment or occupational skills?",
        list(RELEVANCE),
        horizontal=True,
        index=rel_values.index(row["relevance"]) if row["relevance"] else None,
        key=f"relevance:{widget_key}",
    )
    relevance = RELEVANCE.get(rel_choice)
    impact = "unclear"
    if relevance == "relevant":
        impact_values = list(IMPACT.values())
        impact_choice = st.radio(
            "2. What impact does the author express?",
            list(IMPACT),
            horizontal=True,
            index=impact_values.index(row["impact"]) if row["impact"] else None,
            key=f"impact:{widget_key}",
        )
        impact = IMPACT.get(impact_choice)
    elif relevance:
        st.caption("Impact is automatically Unclear for Unrelated or Unclear relevance.")
    note = st.text_input("Note (optional)", row["note"], key=f"note:{widget_key}")
    with st.expander("Quick rules"):
        st.markdown(
            "**Positive:** benefit only. **Negative:** harm or worry only. "
            "**Mixed:** both. **Neutral:** description/question without an evaluation. "
            "**Unclear:** cannot determine.\n\n"
            "Judge only this comment, not whether its claim is true. "
            "Do not infer missing context. Mentioning training alone does not mean pressure."
        )
    if st.button("Save & next →", type="primary", disabled=not relevance or not impact):
        try:
            if review:
                marker = "[model-informed pilot review]"
                if marker not in note:
                    note = f"{note} {marker}".strip()
            save_label(path, row["sample_id"], relevance, impact, note, digest)
        except (OSError, ValueError) as error:
            st.error(f"Not saved: {error}")
        else:
            pending = [i for i in indices if i != index and (review or not rows[i]["relevance"])]
            st.session_state[position_key] = next(
                (i for i in pending if i > index), pending[0] if pending else index
            )
            st.rerun()
    st.caption("Only Save & next writes labels. Navigation leaves unsaved choices uncommitted.")
    if completed == len(rows):
        st.success(
            "All comments saved. The sheet is ready for comparison with the other annotator."
        )


if __name__ == "__main__":
    st.set_page_config(page_title="AMC human annotation", page_icon="✍️")
    render()
