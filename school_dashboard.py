
import streamlit as st
import pandas as pd
from pathlib import Path
from datetime import date, datetime, time
from io import StringIO, BytesIO
import hmac
import os
import gzip
import base64
import urllib.parse
import json
import html
import streamlit.components.v1 as components

st.set_page_config(
    page_title="Sui-Unique Academy",
    page_icon="🎓",
    layout="wide"
)


# ============================================================
# USERNAME, PASSWORD AND ROLE-BASED LOGIN
# ============================================================


def check_password():
    """Authenticate users and assign their access roles."""

    if st.session_state.get("authenticated", False):
        return True

    st.title("Sui-Unique Academy")
    st.subheader("AI-Based Early Warning System")
    st.write("Secure Staff Login")

    with st.form("login_form"):
        username = st.selectbox(
            "Username",
            ["teacher", "management", "admin"],
            index=None,
            placeholder="Select your username"
        )

        password = st.text_input(
            "Password",
            type="password"
        )

        sign_in = st.form_submit_button("Sign In")

    if sign_in:
        if username is None:
            st.error("Please select your username.")
            return False

        users = st.secrets["users"]
        matched_role = None

        for account_name in ("admin", "management", "teacher"):
            account = users[account_name]

            username_matches = hmac.compare_digest(
                username,
                account_name
            )

            password_matches = hmac.compare_digest(
                password,
                account["password"]
            )

            if username_matches and password_matches:
                matched_role = account["role"]

        if matched_role is not None:
            st.session_state["authenticated"] = True
            st.session_state["username"] = username
            st.session_state["role"] = matched_role
            st.rerun()
        else:
            st.error("Invalid username or password.")

    return False


if not check_password():
    st.stop()

# ============================================================
# LOGGED-IN USER AND LOGOUT BUTTON
# ============================================================

with st.sidebar:
    st.write(
        "Logged in as:",
        st.session_state.get("username", "User")
    )

    st.write(
        "Role:",
        st.session_state.get("role", "Unknown")
    )

    if st.button("🚪 Logout"):
        st.session_state["authenticated"] = False
        st.session_state.pop("username", None)
        st.session_state.pop("role", None)
        st.rerun()



# ============================================================
# DATA LOADING
# ============================================================

DATA_DIR = Path("data/real_school_data")


@st.cache_data
def load_attendance():
    local_file = DATA_DIR / "processed_school_attendance.csv"

    if local_file.exists():
        return pd.read_csv(local_file)

    compressed_data = base64.b64decode(
        st.secrets["ATTENDANCE_CSV"]
    )
    csv_data = gzip.decompress(
        compressed_data
    ).decode("utf-8-sig")

    return pd.read_csv(StringIO(csv_data))


@st.cache_data
def load_risk():
    local_file = (
        DATA_DIR / "school_ai_risk_scores_with_status.csv"
    )

    if local_file.exists():
        return pd.read_csv(local_file)

    compressed_data = base64.b64decode(
        st.secrets["RISK_CSV"]
    )
    csv_data = gzip.decompress(
        compressed_data
    ).decode("utf-8-sig")

    return pd.read_csv(StringIO(csv_data))


# ============================================================
# SAVE NEW ATTENDANCE WITHOUT OVERWRITING HISTORICAL RECORDS
# ============================================================

# Streamlit Community Cloud local storage is temporary.
# A database or other persistent storage is needed for
# permanent school attendance records.

NEW_ATTENDANCE_FILE = (
    DATA_DIR / "new_attendance_entries.csv"
)


def get_attendance():
    historical = load_attendance().copy()

    if not NEW_ATTENDANCE_FILE.exists():
        return historical

    new = pd.read_csv(
        NEW_ATTENDANCE_FILE,
        dtype={"Student_ID": str}
    )

    return pd.concat(
        [historical, new],
        ignore_index=True
    )


def save_attendance(record):
    """Append one record without overwriting historical data."""

    NEW_ATTENDANCE_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    if NEW_ATTENDANCE_FILE.exists():
        existing = pd.read_csv(
            NEW_ATTENDANCE_FILE,
            dtype={"Student_ID": str}
        )
    else:
        existing = pd.DataFrame()

    combined = pd.concat(
        [existing, pd.DataFrame([record])],
        ignore_index=True
    )

    temporary = NEW_ATTENDANCE_FILE.with_suffix(".tmp")

    combined.to_csv(
        temporary,
        index=False
    )

    os.replace(
        temporary,
        NEW_ATTENDANCE_FILE
    )


# Keep the complete dataset for duplicate checking and historical review.
all_attendance = get_attendance()

# Preserve missing academic years as unassigned rather than guessing.
if "Academic_Year" not in all_attendance.columns:
    all_attendance["Academic_Year"] = pd.NA
all_attendance["Academic_Year"] = (
    all_attendance["Academic_Year"]
    .astype("string")
    .str.strip()
    .replace({"": pd.NA, "nan": pd.NA, "None": pd.NA})
)

available_years = sorted(
    all_attendance["Academic_Year"].dropna().unique().tolist()
)
missing_year_count = int(all_attendance["Academic_Year"].isna().sum())

st.sidebar.subheader("Academic Year Filter")
year_options = ["All Academic Years"] + available_years
if missing_year_count:
    year_options.append("Unassigned / Missing Year")

selected_year = st.sidebar.selectbox(
    "Select Academic Year",
    year_options,
    index=0,
    key="academic_year_filter",
)

if selected_year == "All Academic Years":
    df = all_attendance.copy()
elif selected_year == "Unassigned / Missing Year":
    df = all_attendance[all_attendance["Academic_Year"].isna()].copy()
else:
    df = all_attendance[
        all_attendance["Academic_Year"].eq(selected_year).fillna(False)
    ].copy()

# Admin-only inspection; does not change or delete stored records.
if st.session_state.get("role") == "admin":
    with st.sidebar.expander("Academic Year Data Check"):
        counts = (
            all_attendance["Academic_Year"]
            .fillna("MISSING")
            .value_counts(dropna=False)
            .rename_axis("Academic Year")
            .reset_index(name="Number of Records")
        )
        st.dataframe(counts, hide_index=True)
        if missing_year_count:
            st.warning(
                f"{missing_year_count} records have no academic year. "
                "They have not been assigned to any year automatically."
            )

# ============================================================
# SIDEBAR NAVIGATION
# ============================================================

st.sidebar.title("School Dashboard")

user_role = str(st.session_state.get("role", "teacher")).strip().lower()
is_leadership = user_role in ("management", "admin")

# Teachers only see follow-ups when the selected year has a recorded
# punctuality concern. This is calculated from year-filtered attendance,
# rather than hard-coding a particular academic year.
attendance_status = df["Attendance_Status"].astype(str).str.strip().str.lower()
late_calculated = df["Late_Calculated"].astype(str).str.strip().str.lower() if "Late_Calculated" in df.columns else pd.Series(False, index=df.index)
has_lateness_to_follow_up = bool((attendance_status.eq("late") | late_calculated.eq("yes")).any())

navigation = ["Student Attendance", "Early Warnings"]
if user_role == "teacher":
    navigation.append("My Escalations")

else:
    navigation.insert(0, "Overview")
    navigation.append("Escalation Register")

    if user_role == "admin":
        navigation.append("Parent Communication")

    navigation.append("Management Reports")

selected_page = st.sidebar.radio(
    "Choose a Section",
    navigation
)

st.sidebar.divider()
st.sidebar.caption(
    "Sui-Unique Academy | Research Prototype"
)

st.title("🎓 Sui-Unique Academy")
st.caption(
    "Student Attendance & Early Warning System-"
    "Research Prototype"
)


# ============================================================
# MANAGEMENT PDF REPORTING — ACTUAL YEAR-TAGGED RECORDS ONLY
# ============================================================

def make_yearly_attendance_summary(attendance):
    """Summarise recorded observations; never infer unrecorded days."""
    source = attendance.copy()
    source["Academic_Year"] = source["Academic_Year"].astype("string").str.strip()
    source = source[source["Academic_Year"].notna() & source["Academic_Year"].ne("")].copy()
    source["Student_ID"] = source["Student_ID"].astype(str).str.strip().str.upper()
    state = source["Attendance_Status"].astype(str).str.strip().str.lower()
    calculated = (source["Late_Calculated"].astype(str).str.strip().str.lower().eq("yes")
                  if "Late_Calculated" in source.columns else pd.Series(False, index=source.index))
    source["_late"] = state.eq("late") | calculated
    source["_absent"] = state.eq("absent")
    source["_date"] = pd.to_datetime(source["Date"], errors="coerce")
    rows = []
    for year, part in source.groupby("Academic_Year"):
        total = len(part)
        late = int(part["_late"].sum())
        absent = int(part["_absent"].sum())
        rows.append({
            "Academic year": str(year), "Students": int(part["Student_ID"].nunique()),
            "Recorded days": total, "Late": late, "Absent": absent,
            "Late share (%)": round(100 * late / total, 1) if total else 0.0,
            "First record": part["_date"].min().strftime("%d %b %Y") if part["_date"].notna().any() else "Unknown",
            "Last record": part["_date"].max().strftime("%d %b %Y") if part["_date"].notna().any() else "Unknown",
        })
    return pd.DataFrame(rows), source


def build_management_pdf(summary, observations):
    """Generate a self-contained management PDF without writing student data to disk."""
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.units import inch
    from xml.sax.saxutils import escape

    output = BytesIO()
    doc = SimpleDocTemplate(output, pagesize=(595.28, 841.89), rightMargin=42,
                            leftMargin=42, topMargin=45, bottomMargin=45)
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="ReportTitleSU", parent=styles["Title"], fontSize=17,
                              textColor=colors.HexColor("#17365D"), spaceAfter=10))
    styles.add(ParagraphStyle(name="ReportSmallSU", parent=styles["Normal"], fontSize=9, leading=13))
    story = [Paragraph("Sui-Unique Academy", styles["ReportTitleSU"]),
             Paragraph("Management Attendance Trends and Support Report", styles["Heading2"]),
             Paragraph("Generated: " + datetime.now().strftime("%d %B %Y"), styles["ReportSmallSU"]), Spacer(1, 12)]
    story.append(Paragraph("Executive overview", styles["Heading2"]))
    story.append(Paragraph("This report compares available recorded attendance by academic year. "
                           "It does not assume that missing days are punctual or that years with unequal "
                           "record coverage are directly comparable.", styles["ReportSmallSU"]))
    story.append(Spacer(1, 12))
    if summary.empty:
        story.append(Paragraph("No academic-year-labelled attendance records are available.", styles["Normal"]))
    else:
        rows = [["Year", "Students", "Records", "Late", "Absent", "Late %"]]
        for _, r in summary.sort_values("Academic year").iterrows():
            rows.append([str(r["Academic year"]), str(r["Students"]), str(r["Recorded days"]),
                         str(r["Late"]), str(r["Absent"]), f'{r["Late share (%)"]:.1f}%'])
        table = Table(rows, colWidths=[100, 65, 78, 65, 65, 68], repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#17365D")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 9),
            ("TOPPADDING", (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 1), (-1, -1), 7),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.white]),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.lightgrey),
        ]))
        story.append(table)
        story.append(Spacer(1, 10))
        for _, r in summary.sort_values("Academic year").iterrows():
            year = escape(str(r["Academic year"]))
            story.append(Paragraph(
                f'<b>{year}:</b> {r["Recorded days"]} records from {r["Students"]} students, '
                f'{r["Late"]} late arrivals and {r["Absent"]} absences. '
                f'Record coverage: {escape(str(r["First record"]))} to {escape(str(r["Last record"]))}.',
                styles["ReportSmallSU"]))
            story.append(Spacer(1, 5))
        story.append(Spacer(1, 10))
        story.append(Paragraph("Year-on-year interpretation", styles["Heading2"]))
        if len(summary) >= 2:
            a, b = summary.sort_values("Academic year").iloc[-2:].to_dict("records")
            delta = b["Late share (%)"] - a["Late share (%)"]
            story.append(Paragraph(
                f'The recorded late-arrival share changed by {delta:+.1f} percentage points '
                f'from {escape(str(a["Academic year"]))} to {escape(str(b["Academic year"]))}. '
                'This is a descriptive difference, not evidence of improvement or deterioration, '
                'because student counts, record volumes and observation periods may differ.',
                styles["ReportSmallSU"]))
        else:
            story.append(Paragraph("Only one labelled academic year is available; a two-year comparison "
                                   "cannot yet be made.", styles["ReportSmallSU"]))

        story.append(Spacer(1, 10))
        story.append(Paragraph("Monthly lateness trend", styles["Heading2"]))
        valid = observations.dropna(subset=["_date"]).copy()
        if not valid.empty:
            valid["_month"] = valid["_date"].dt.strftime("%Y-%m")
            monthly = valid.groupby(["Academic_Year", "_month"], dropna=True).agg(
                recorded=("_late", "size"), late=("_late", "sum")).reset_index()
            monthly["late_pct"] = (monthly["late"] / monthly["recorded"] * 100).round(1)
            data = [["Academic year", "Month", "Records", "Late", "Late %"]]
            for _, r in monthly.sort_values(["Academic_Year", "_month"]).tail(30).iterrows():
                data.append([str(r["Academic_Year"]), str(r["_month"]),
                             str(int(r["recorded"])), str(int(r["late"])), f'{r["late_pct"]:.1f}%'])
            trend = Table(data, colWidths=[115, 105, 80, 70, 70], repeatRows=1)
            trend.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E7EEF5")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.whitesmoke]),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
            ]))
            story.append(trend)
        else:
            story.append(Paragraph("No valid dated attendance records are available for monthly trends.", styles["ReportSmallSU"]))

    story.append(Spacer(1, 12))
    story.append(Paragraph("Recommended management actions", styles["Heading2"]))
    recommendations = [
        "Maintain daily attendance entry and verify missing records before drawing conclusions.",
        "Review students with repeated lateness privately and explore transport, family or timetable barriers.",
        "Contact parents or guardians supportively and document agreed interventions and review dates.",
        "Review lateness patterns by term and month; check whether interventions reduce repeat lateness.",
        "Do not treat experimental AI scores as validated individual predictions or disciplinary evidence.",
    ]
    for i, item in enumerate(recommendations, 1):
        story.append(Paragraph(f"{i}. {escape(item)}", styles["ReportSmallSU"]))
        story.append(Spacer(1, 5))
    story.append(Spacer(1, 12))
    story.append(Paragraph("Data interpretation note", styles["Heading2"]))
    story.append(Paragraph(
        "Counts reflect the attendance entries available when this PDF was generated. "
        "The late percentage uses all recorded entries as its denominator. "
        "Academic-year labels, duplicate entries, incomplete records and differing coverage "
        "should be verified before using the figures for formal school decisions. "
        "This report is descriptive, not an AI prediction report.", styles["ReportSmallSU"]))
    doc.build(story)
    output.seek(0)
    return output.getvalue()


# ============================================================
# SECTION 1: OVERVIEW
# ============================================================

if selected_page == "Overview":

    st.header("Attendance Overview")
    st.caption(f"Academic year: {selected_year}")
    if selected_year == "All Academic Years":
        st.info("Totals include all academic years. Select a specific year in the sidebar to compare records separately.")

    c1, c2, c3, c4 = st.columns(4)

    c1.metric(
        "Students in Records",
        df["Student_ID"].nunique()
    )

    c2.metric(
        "Attendance Records",
        len(df)
    )

    c3.metric(
        "Recorded Late Arrivals",
        int(df["Late_Calculated"].eq("Yes").sum())
    )

    c4.metric(
        "Recorded Absences",
        int(df["Attendance_Status"].eq("Absent").sum())
    )



    st.subheader("Recorded Attendance by Term")

    term_summary = (
        df.groupby(["Academic_Year", "Term"], dropna=False)
        .agg(
            Students=("Student_ID", "nunique"),
            Attendance_Entries=("Student_ID", "size")
        )
        .reset_index()
    )

    st.dataframe(
        term_summary,
        hide_index=True,
        width="stretch"
    )


# ============================================================
# SECTION 2: STUDENT ATTENDANCE
# ============================================================

elif selected_page == "Student Attendance":

    st.header("Student Attendance")
    st.caption(f"Viewing attendance for: {selected_year}")

    st.divider()

    st.subheader("📝 Daily Student Attendance Entry")

    st.caption(
        "Entries are saved to this application's local CSV "
        "and appear in totals immediately."
    )



    if st.session_state.pop("attendance_saved", False):
        st.success(
            "Attendance saved. The attendance totals and "
            "student lookup have been updated."
        )

    current_year = date.today().year

    student_ids = sorted(
        load_attendance()["Student_ID"]
        .dropna()
        .astype(str)
        .unique()
        .tolist()
    )

    # --------------------------------------------------------
    # DAILY ATTENDANCE FORM
    # --------------------------------------------------------

    
    
    with st.form("daily_attendance_form"):

        # FIRST ROW: Four fields
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            academic_year = st.selectbox(
                "Academic Year",
                sorted(set(available_years + [
                    f"{current_year-1}/{current_year}",
                    f"{current_year}/{current_year+1}",
                    f"{current_year+1}/{current_year+2}"
                ])),
                index=None,
                placeholder="Choose the academic year"
            )

        with col2:
            entry_term = st.selectbox(
                "Term",
                ["First term", "Second term", "Third term"]
            )

        with col3:
            entry_date = st.date_input(
                "Attendance Date",
                value=date.today()
            )

        with col4:
            entry_student = st.text_input(
                "Student ID",
                placeholder="e.g. SUA 041"
            )

        # SECOND ROW: Three fields
        col5, col6, col7 = st.columns(3)

        with col5:
            entry_class = st.selectbox(
                "Class",
                ["JSS1", "JSS2", "JSS3", "SS1", "SS2", "SS3"]
            )

        with col6:
            entry_status = st.selectbox(
                "Attendance Status",
                ["Present", "Late", "Absent"]
            )

        with col7:
            entry_arrival = st.time_input(
                "Arrival Time",
                value=time(7, 30)
            )

        submitted_attendance = st.form_submit_button(
            "💾 Save Attendance",
            width="stretch"
        )


    # --------------------------------------------------------
    # PROCESS AND SAVE ATTENDANCE
    # --------------------------------------------------------

    
    # ========================================================
    # PROCESS AND SAVE ATTENDANCE
    # ========================================================

    if submitted_attendance:

        entry_student = entry_student.strip().upper()

        # Validate Student ID
        if not entry_student:
            st.error("Please enter a Student ID before saving.")
        elif not academic_year:
            st.error("Please select an Academic Year before saving.")
        elif entry_date.year not in [int(y) for y in academic_year.split("/")]:
            st.error("Attendance date does not match the selected academic year. Nothing was saved.")
        else:
            cutoff = time(7, 30)

            # Determine attendance status
            if entry_status == "Absent":
                calculated_status = "Absent"
                minutes_late = 0
                arrival = ""

            else:
                if entry_status == "Late" and entry_arrival <= cutoff:
                    st.error(
                        "A student marked Late must have an "
                        "arrival time after 7:30 a.m."
                    )
                    st.stop()

                calculated_status = (
                    "Late" if entry_arrival > cutoff else "Present"
                )

                minutes_late = max(
                    0,
                    int(
                        (
                            datetime.combine(entry_date, entry_arrival)
                            - datetime.combine(entry_date, cutoff)
                        ).total_seconds() // 60
                    )
                )

                arrival = entry_arrival.strftime("%H:%M")

            # Check for duplicate attendance records
            recorded_dates = pd.to_datetime(
                all_attendance["Date"],
                errors="coerce"
            ).dt.date

            already_recorded = (
                all_attendance["Student_ID"]
                .astype(str)
                .str.strip()
                .str.upper()
                .eq(entry_student)
                &
                recorded_dates.eq(entry_date)
            ).any()

            if already_recorded:
                st.error(
                    f"Attendance for {entry_student} on "
                    f"{entry_date} already exists. "
                    "Nothing was saved."
                )

            else:
                # Prepare the new attendance record
                record = {
                    "Academic_Year": academic_year,
                    "Student_ID": entry_student,
                    "Class": entry_class,
                    "Term": entry_term,
                    "Week": entry_date.isocalendar().week,
                    "Date": entry_date.isoformat(),
                    "Arrival_Time": arrival,
                    "Attendance_Status": calculated_status,
                    "Minutes_Late": minutes_late,
                    "Late_Calculated": (
                        "Yes" if calculated_status == "Late" else "No"
                    )
                }

                # Save the attendance record
                try:
                    save_attendance(record)

                except Exception as exc:
                    st.error(
                        f"Attendance could not be saved: {exc}"
                    )

                else:
                    st.success(
                        f"Attendance for {entry_student} "
                        "saved successfully!"
                    )

                    st.session_state["attendance_saved"] = True
                    st.rerun()


    # --------------------------------------------------------
    # CURRENT ATTENDANCE TOTALS
    # --------------------------------------------------------

    st.subheader("Current Attendance Totals")

    total_col, late_col, absent_col = st.columns(3)

    total_col.metric(
        "Total Recorded Attendance",
        len(df)
    )

    late_col.metric(
        "Late Arrivals",
        int(df["Late_Calculated"].eq("Yes").sum())
    )

    absent_col.metric(
        "Absences",
        int(df["Attendance_Status"].eq("Absent").sum())
    )

    # --------------------------------------------------------
    # FILTER ATTENDANCE RECORDS
    # --------------------------------------------------------

    st.divider()

    term = st.selectbox(
        "Select Term",
        ["All Terms"]
        +
        sorted(
            df["Term"].dropna().unique().tolist()
        )
    )

    if term == "All Terms":
        filtered = df
    else:
        filtered = df[df["Term"] == term]

    chosen_class = st.selectbox(
        "Select Class",
        ["All Classes"]
        +
        sorted(
            filtered["Class"].dropna().unique().tolist()
        )
    )

    if chosen_class != "All Classes":
        filtered = filtered[
            filtered["Class"] == chosen_class
        ]

    if is_leadership:
        st.subheader("Attendance Records")
    else:
        st.caption("Attendance records can be viewed below when needed.")
    with st.expander("View attendance records", expanded=False):
        st.dataframe(
            filtered[
            [
                "Student_ID",
                "Class",
                "Academic_Year",
                "Term",
                "Week",
                "Date",
                "Arrival_Time",
                "Attendance_Status",
                "Minutes_Late"
            ]
        ],
        hide_index=True,
        width="stretch"
    )

    st.caption(
        "Missing school days are not assumed punctual."
    )

    # --------------------------------------------------------
    # FIND A STUDENT
    # --------------------------------------------------------

    st.divider()

    st.subheader("🔎 Find a Student")

    search = st.text_input(
        "Enter Student ID",
        placeholder="SUA 001"
    )

    if search.strip():

        student = df[
            df["Student_ID"]
            .astype(str)
            .str.strip()
            .str.upper()
            ==
            search.strip().upper()
        ].copy()

        if student.empty:

            st.warning(
                "No student found with that ID."
            )

        else:

            student["Date"] = pd.to_datetime(
                student["Date"],
                errors="coerce"
            )

            student = student.sort_values("Date")

            a, b, c = st.columns(3)

            a.metric(
                "Recorded Days",
                len(student)
            )

            b.metric(
                "Late Arrivals",
                int(
                    student["Late_Calculated"]
                    .eq("Yes")
                    .sum()
                )
            )

            c.metric(
                "Absences",
                int(
                    student["Attendance_Status"]
                    .eq("Absent")
                    .sum()
                )
            )

            st.dataframe(
                student[
                    [
                        "Date",
                        "Academic_Year",
                        "Term",
                        "Week",
                        "Arrival_Time",
                        "Attendance_Status",
                        "Minutes_Late"
                    ]
                ],
                hide_index=True,
                width="stretch"
            )

    # --------------------------------------------------------
    # STUDENT ATTENDANCE LOOKUP
    # --------------------------------------------------------

    st.divider()

    if is_leadership:
        st.subheader("📋 Student Attendance Lookup")

        lookup_class = st.selectbox(
            "1. Select Class",
            sorted(
                df["Class"].dropna().unique()
            ),
            key="lookup_class"
        )

        lookup_term = st.selectbox(
            "2. Select Term",
            sorted(
                df["Term"].dropna().unique().tolist()
            ),
            key="lookup_term"
        )

        matching = df[
            (df["Class"] == lookup_class)
            &
            (df["Term"] == lookup_term)
        ]

        ids = sorted(
            matching["Student_ID"]
            .dropna()
            .unique()
        )

        if not ids:

            st.warning(
                "No student records found for this "
                "class and term."
            )

        else:

            sid = st.selectbox(
                "3. Select Student ID",
                ids,
                key="lookup_student"
            )

            student_data = matching[
                matching["Student_ID"] == sid
            ]

            a, b, c = st.columns(3)

            a.metric(
                "Recorded Days",
                len(student_data)
            )

            b.metric(
                "Late Arrivals",
                int(
                    student_data["Late_Calculated"]
                    .eq("Yes")
                    .sum()
                )
            )

            c.metric(
                "Absences",
                int(
                    student_data["Attendance_Status"]
                    .eq("Absent")
                    .sum()
                )
            )

            st.dataframe(
                student_data[
                    [
                        "Date",
                        "Week",
                        "Arrival_Time",
                        "Attendance_Status",
                        "Minutes_Late"
                    ]
                ].sort_values("Date"),
                hide_index=True,
                width="stretch"
            )


# ============================================================
# SECTION 3: EARLY WARNINGS — YEAR-SCOPED, ROLE-AWARE
# ============================================================

elif selected_page == "Early Warnings":
    st.header("🔔 Student Attendance Support")
    st.caption(f"Academic year: {selected_year}")

    if selected_year in ("All Academic Years", "Unassigned / Missing Year"):
        st.info("Select one academic year in the sidebar to review its students and attendance.")
    else:
        year_data = df.copy()
        year_data["Student_ID"] = year_data["Student_ID"].astype(str).str.strip().str.upper()
        year_data["Term_Normalized"] = (
            year_data["Term"].astype(str).str.strip().str.lower()
            .str.replace(r"\s+", " ", regex=True)
        )
        term_options = ["All Terms"] + sorted(year_data["Term_Normalized"].dropna().unique().tolist())
        selected_term = st.selectbox("Term", term_options, key="support_term")
        if selected_term != "All Terms":
            year_data = year_data[year_data["Term_Normalized"] == selected_term].copy()

        status = year_data["Attendance_Status"].astype(str).str.strip().str.lower()
        late_flag = year_data["Late_Calculated"].astype(str).str.strip().str.lower().eq("yes") | status.eq("late")
        year_data["Is_Late"] = late_flag
        year_data["Is_Absent"] = status.eq("absent")
        student_count = year_data["Student_ID"].nunique()
        late_total = int(year_data["Is_Late"].sum())
        absent_total = int(year_data["Is_Absent"].sum())

        a, b, c = st.columns(3)
        a.metric("Students Recorded", student_count)
        b.metric("Late Arrivals Recorded", late_total)
        c.metric("Absences Recorded", absent_total)

        if year_data.empty:
            st.info("No attendance records are available for this academic year and term.")
        else:
            # Statuses use observed attendance only, NOT experimental AI scores.
            # Persistent lateness: 3+ late days per week for 4 consecutive weeks.
            # Missing days are never assumed to be on-time.
            year_data["Parsed_Date"] = pd.to_datetime(year_data["Date"], errors="coerce")
            year_data["Week_Start"] = (
                year_data["Parsed_Date"]
                - pd.to_timedelta(year_data["Parsed_Date"].dt.weekday, unit="D")
            ).dt.normalize()
            summaries = []
            for sid, records in year_data.groupby("Student_ID"):
                recorded_late = int(records["Is_Late"].sum())
                recorded_absent = int(records["Is_Absent"].sum())
                weekly = (
                    records.dropna(subset=["Week_Start"])
                    .groupby("Week_Start")["Is_Late"].sum().sort_index()
                )
                # Only actual recorded weeks count; no artificial zero-filled weeks.
                consecutive = 0
                longest = 0
                previous_week = None
                for week_start, late_days in weekly.items():
                    if int(late_days) >= 3:
                        consecutive = consecutive + 1 if (previous_week is not None and (week_start - previous_week).days == 7) else 1
                        longest = max(longest, consecutive)
                    else:
                        consecutive = 0
                    previous_week = week_start
                if longest >= 4:
                    level = "🔴 Urgent review"
                    explanation = "Persistent lateness detected. Please take action."
                elif (weekly >= 2).any() or recorded_late >= 3:
                    level = "🟡 Early warning"
                    explanation = "Repeated lateness detected. Please monitor."
                elif len(weekly) < 4:
                    level = "⚪ Insufficient records"
                    explanation = "Insufficient attendance records. Please continue monitoring."
                else:
                    level = "🟢 On track in records"
                    explanation = "Attendance is on track. Continue monitoring."
                summaries.append({
                    "Student ID": sid,
                    "Status": level,
                    "Late arrivals": recorded_late,
                    "Absences": recorded_absent,
                    "Recorded days": len(records),
                    "Explanation": explanation,
                })
            support = pd.DataFrame(summaries)
            st.subheader("🚦 Punctuality traffic lights")
            st.caption("Based on recorded attendance in the selected academic year and term; not a validated AI prediction.")
            order = {"🔴 Urgent review": 0, "🟡 Early warning": 1, "⚪ Insufficient records": 2, "🟢 On track in records": 3}
            support["_order"] = support["Status"].map(order)
            support = support.sort_values(["_order", "Student ID"]).drop(columns="_order")
            counts = support["Status"].value_counts()
            red, yellow, green = st.columns(3)
            red.metric("🔴 Urgent", int(counts.get("🔴 Urgent review", 0)))
            yellow.metric("🟡 Early warning", int(counts.get("🟡 Early warning", 0)))
            green.metric("🟢 On track", int(counts.get("🟢 On track in records", 0)))
            missing_count = int(counts.get("⚪ Insufficient records", 0))
            if missing_count:
                st.caption(f"Insufficient records: {missing_count} student(s) — not a fourth traffic light.")
            with st.expander("View student traffic-light table", expanded=False):
                st.dataframe(support[["Student ID", "Status", "Late arrivals"]], hide_index=True, use_container_width=True)

            st.subheader("🔊 Listen to a student attendance alert")
            student_ids = support["Student ID"].tolist()
            selected_student = st.selectbox("Choose a student", student_ids, key="support_student")
            selected_info = support.loc[support["Student ID"] == selected_student].iloc[0]
            st.write(f"**{selected_student}: {selected_info['Status']}**")
            st.write(selected_info["Explanation"])
            # Speech is user-initiated; no automatic playback, external API or audio upload.
            # Avoid speaking the student ID in a shared classroom.
            alert_text = "Attention! " + str(selected_info["Explanation"])
            safe_text = json.dumps(alert_text).replace("<", "\\u003c").replace(">", "\\u003e")
            components.html(
                f"""<!doctype html><html><body style='margin:0;font-family:sans-serif'>
                <button id='speak' style='padding:10px 16px;border-radius:8px;border:1px solid #888;cursor:pointer'>🔊 Hear alert</button>
                <button id='stop' style='padding:10px 16px;border-radius:8px;border:1px solid #888;cursor:pointer'>Stop</button>
                <span id='feedback' style='font-size:12px;margin-left:8px'></span>
                <script>
                const msg = {safe_text};
                document.getElementById('speak').onclick = () => {{
                    if (!('speechSynthesis' in window)) {{ document.getElementById('feedback').textContent = 'Speech is not supported by this browser.'; return; }}
                    speechSynthesis.cancel();
                    const utterance = new SpeechSynthesisUtterance(msg);
                    const voices = speechSynthesis.getVoices();
                    const preferred = voices.find(v => v.lang.toLowerCase().replace('_','-') === 'en-ng')
                        || voices.find(v => /nigerian|nigeria/i.test(v.name) && v.lang.toLowerCase().startsWith('en'));
                    const fallback = voices.find(v => v.lang.toLowerCase().startsWith('en-gb'))
                        || voices.find(v => v.lang.toLowerCase().startsWith('en'));
                    if (preferred || fallback) utterance.voice = preferred || fallback;
                    utterance.lang = preferred ? 'en-NG' : (fallback ? fallback.lang : 'en-GB');
                    utterance.rate = 0.90; utterance.pitch = 1.0;
                    document.getElementById('feedback').textContent = preferred ? 'Nigerian English voice' : 'English voice (Nigerian voice unavailable)';
                    utterance.onerror = () => {{ document.getElementById('feedback').textContent = 'Could not play audio in this browser.'; }};
                    speechSynthesis.speak(utterance);
                }};
                document.getElementById('stop').onclick = () => speechSynthesis?.cancel();
                </script></body></html>""",
                height=65,
            )
            st.caption("Click Hear alert to play. Nigerian English is preferred when available on your device; otherwise an English voice is used. No student name is spoken.")

            with st.expander("View selected student's attendance records", expanded=False):
                student_rows = year_data[year_data["Student_ID"] == selected_student].copy()
                student_rows = student_rows.sort_values("Parsed_Date", ascending=False)
                st.write(f"{len(student_rows)} recorded days · {int(student_rows['Is_Late'].sum())} late arrivals · {int(student_rows['Is_Absent'].sum())} absences")
                st.dataframe(student_rows[["Date", "Term", "Arrival_Time", "Attendance_Status"]], hide_index=True, use_container_width=True)

        if user_role == "teacher":
            st.caption("To request parent contact, use My Escalations. Only the administrator can prepare WhatsApp messages.")
        else:
            st.caption("Parent communication is managed by the administrator in the Parent Communication section.")


# ============================================================
# SECTION 4: STUDENT FOLLOW-UPS
# ============================================================

# School workflow: teacher raises a concern, administrator reviews and contacts parents.
ESCALATIONS_FILE = DATA_DIR / "attendance_escalations.csv"
ESCALATION_COLUMNS = ["Academic_Year", "Student_ID", "Created_At", "Raised_By", "Concern", "Status", "Admin_Note", "Parent_Contact_Date", "Follow_Up_Date"]

def load_escalations():
    if not ESCALATIONS_FILE.exists():
        return pd.DataFrame(columns=ESCALATION_COLUMNS)
    try:
        records = pd.read_csv(ESCALATIONS_FILE, dtype=str).fillna("")
        for col in ESCALATION_COLUMNS:
            if col not in records.columns:
                records[col] = ""
        return records[ESCALATION_COLUMNS]
    except (OSError, pd.errors.EmptyDataError) as exc:
        st.error(f"Could not read the escalation register: {exc}")
        return pd.DataFrame(columns=ESCALATION_COLUMNS)

def save_escalations(data):
    ESCALATIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = ESCALATIONS_FILE.with_suffix(".tmp")
    data.to_csv(tmp, index=False)
    os.replace(tmp, ESCALATIONS_FILE)

def year_escalations():
    records = load_escalations()
    if selected_year not in ("All Academic Years", "Unassigned / Missing Year"):
        records = records[records["Academic_Year"].eq(selected_year)]
    return records

# Admin-only indicator, using actual saved teacher reports for the selected year.
if user_role == "admin":
    pending_reports = year_escalations()
    pending_reports = pending_reports[
        pending_reports["Status"].eq("Pending Review")
        & pending_reports["Raised_By"].str.strip().str.lower().eq("teacher")
    ]
    with st.sidebar:
        st.divider()
        st.metric("New Teacher Escalations", len(pending_reports))
        if not pending_reports.empty:
            st.info("Open Escalation Register to review new reports.")

if selected_page == "My Escalations" and user_role == "teacher":
    st.header("Escalate an Attendance Concern")
    st.caption("Teachers record concerns; only administrators contact parents. No message is sent automatically.")
    if selected_year in ("All Academic Years", "Unassigned / Missing Year"):
        st.info("Select a specific academic year before raising a concern.")
    else:
        recent = df.copy()
        recent["_late"] = recent["Attendance_Status"].astype(str).str.lower().eq("late")
        if "Late_Calculated" in recent.columns:
            recent["_late"] |= recent["Late_Calculated"].astype(str).str.lower().eq("yes")
        eligible = sorted(recent.loc[recent["_late"], "Student_ID"].dropna().astype(str).unique())
        if not eligible:
            st.success("No recorded lateness concerns to escalate for this academic year.")
        else:
            with st.form("raise_escalation"):
                sid = st.selectbox("Student with recorded lateness", eligible)
                concern = st.text_area("Brief observation", placeholder="Describe the attendance concern and any support already provided")
                submit = st.form_submit_button("Escalate to Administrator")
            if submit:
                if not concern.strip():
                    st.warning("Please provide a brief observation.")
                else:
                    data = load_escalations()
                    duplicate = data[ data["Academic_Year"].eq(selected_year) & data["Student_ID"].eq(sid) & data["Status"].isin(["Pending Review", "Parent Contacted", "Under Monitoring"]) ]
                    if not duplicate.empty:
                        st.warning("An active escalation already exists for this student and year.")
                    else:
                        row = {"Academic_Year":selected_year,"Student_ID":sid,"Created_At":datetime.now().isoformat(timespec="seconds"),"Raised_By":"teacher","Concern":concern.strip(),"Status":"Pending Review","Admin_Note":"","Parent_Contact_Date":"","Follow_Up_Date":""}
                        save_escalations(pd.concat([data,pd.DataFrame([row])],ignore_index=True))
                        st.success("Concern escalated to the administrator.")
    records = year_escalations()
    if not records.empty:
        with st.expander("View escalation status", expanded=False):
            st.dataframe(records[["Academic_Year","Student_ID","Created_At","Status","Follow_Up_Date"]], hide_index=True, use_container_width=True)

elif selected_page == "Escalation Register" and is_leadership:
    st.header("Teacher Escalations — Administrator Review" if user_role == "admin" else "Attendance Escalation Register")
    records = year_escalations()
    if user_role == "admin":
        st.metric("Awaiting Administrator Review", int(records["Status"].eq("Pending Review").sum()))
        st.caption("Reports submitted by teachers are listed below. Select a case to update its status and follow-up actions.")
    else:
        st.caption("Management can view recorded escalations. Case updates are restricted to administrators.")
    if records.empty:
        st.info("No attendance concerns have been escalated for this selection.")
    else:
        st.dataframe(records, hide_index=True, use_container_width=True)
        if user_role == "admin":
            st.caption("Update case status below. A parent contact date must be entered only after actual contact.")
            with st.form("update_escalation"):
                options = [f"{i}: {r.Student_ID} — {r.Status}" for i,r in records.iterrows()]
                choice = st.selectbox("Escalation", options)
                idx = int(choice.split(":",1)[0])
                status = st.selectbox("Status", ["Pending Review","Parent Contacted","Under Monitoring","Resolved"])
                note = st.text_area("Administrator note")
                contact_date = st.date_input("Parent contact date (only if contact was made)", value=None)
                review_date = st.date_input("Next review date (optional)", value=None)
                submitted = st.form_submit_button("Save Case Update")
            if submitted:
                all_cases = load_escalations()
                # Match by unique creation timestamp and student/year, not filtered row position.
                original = records.loc[idx]
                mask = (all_cases["Created_At"].eq(original["Created_At"]) & all_cases["Student_ID"].eq(original["Student_ID"]) & all_cases["Academic_Year"].eq(original["Academic_Year"]))
                if mask.sum() != 1:
                    st.error("Unable to identify this case uniquely; no change saved.")
                elif status == "Parent Contacted" and contact_date is None:
                    st.error("Enter the actual parent contact date before selecting Parent Contacted.")
                else:
                    all_cases.loc[mask,"Status"] = status
                    all_cases.loc[mask,"Admin_Note"] = note.strip()
                    if contact_date is not None:
                        all_cases.loc[mask,"Parent_Contact_Date"] = str(contact_date)
                    if review_date is not None:
                        all_cases.loc[mask,"Follow_Up_Date"] = str(review_date)
                    save_escalations(all_cases)
                    st.success("Case updated. Refresh to view the latest register.")

elif selected_page == "Parent Communication" and user_role == "admin":
    st.header("Administrator Parent Communication")
    st.caption("Only an administrator can prepare a message. Opening WhatsApp does not mean a message was sent.")
    cases = year_escalations()
    cases = cases[cases["Status"].isin(["Pending Review", "Parent Contacted", "Under Monitoring"])]
    if cases.empty:
        st.info("No active escalated concerns require parent communication.")
    else:
        choice = st.selectbox("Escalated student", [f"{r.Student_ID} — {r.Academic_Year} ({r.Status})" for r in cases.itertuples()])
        phone = st.text_input("Verified parent or guardian WhatsApp number", placeholder="08012345678")
        message = st.text_area("Review message", value="Good day, Parent/Guardian.\n\nWe would like to discuss an attendance concern regarding your child. Kindly contact the class teacher to discuss appropriate support.\n\nThank you.\nSchool Administration, Sui-Unique Academy", height=175)
        number = "".join(c for c in phone if c.isdigit())
        if number.startswith("0") and len(number)==11:
            number = "234" + number[1:]
        if number.startswith("234") and len(number)==13 and message.strip():
            st.link_button("Open WhatsApp for administrator review", f"https://wa.me/{number}?text={urllib.parse.quote(message)}")
            st.caption("After sending, record the actual contact date in Escalation Register.")
        else:
            st.info("Enter a valid Nigerian number and review the message to enable WhatsApp.")



# ============================================================
# SECTION 5: MANAGEMENT REPORTS (MANAGEMENT / ADMIN ONLY)
# ============================================================

elif selected_page == "Management Reports" and is_leadership:
    st.header("📄 Management Attendance Reports")
    st.caption("Download a two-year attendance comparison and recommended actions as a PDF.")
    yearly_summary, report_observations = make_yearly_attendance_summary(all_attendance)
    if yearly_summary.empty:
        st.warning("No academic-year-labelled attendance records are available for reporting.")
    else:
        st.subheader("Academic-year comparison")
        st.dataframe(yearly_summary, hide_index=True, use_container_width=True)
        if len(yearly_summary) >= 2:
            st.subheader("Recorded lateness trend")
            chart = yearly_summary.set_index("Academic year")[["Late share (%)"]]
            st.bar_chart(chart)
        else:
            st.info("A two-year comparison will appear when at least two academic years have records.")
        st.info("Yearly figures describe available records only. A year with few records cannot yet be compared fairly with a completed year.")
        st.subheader("Recommended actions")
        st.write("Verify attendance completeness; identify repeated lateness early; speak privately with students and parents; document support; review progress regularly.")
        try:
            pdf_bytes = build_management_pdf(yearly_summary, report_observations)
            if not isinstance(pdf_bytes, bytes) or not pdf_bytes.startswith(b"%PDF-"):
                raise ValueError("PDF generation did not return valid PDF bytes.")

            report_filename = "Sui_Unique_Management_Attendance_Report.pdf"
            st.download_button(
                "📥 Download Management Report (PDF)",
                data=pdf_bytes,
                file_name=report_filename,
                mime="application/pdf",
                use_container_width=True,
                key="management_pdf_download",
            )

            # Backup for browsers that fail to fetch Streamlit's temporary download URL.
            # The report is generated on the local computer, without sending data online.
            reports_dir = Path(__file__).resolve().parent / "management_reports"
            report_path = reports_dir / report_filename
            try:
                reports_dir.mkdir(parents=True, exist_ok=True)
                temporary_report = report_path.with_suffix(".pdf.tmp")
                temporary_report.write_bytes(pdf_bytes)
                os.replace(temporary_report, report_path)
                st.success("A backup PDF has also been saved on this computer.")
                st.code(str(report_path), language=None)
                st.caption("If Chrome says 'Failed – No file', copy this path into Windows File Explorer to open the saved PDF.")
            except OSError as save_error:
                st.warning(f"Could not save the local backup PDF: {save_error}")

        except ImportError:
            st.error("PDF generation requires ReportLab. Install it using: python -m pip install reportlab")
        except Exception as exc:
            st.error(f"Unable to generate the PDF: {exc}")
