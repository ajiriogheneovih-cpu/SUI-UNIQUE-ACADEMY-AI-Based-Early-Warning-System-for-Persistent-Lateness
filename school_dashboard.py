
import streamlit as st
import pandas as pd
from pathlib import Path
from datetime import date, datetime, time
from io import StringIO
import hmac
import os
import gzip
import base64
import urllib.parse

st.set_page_config(
    page_title="Sui-Unique Academy",
    page_icon="🎓",
    layout="wide"
)

# ============================================================
# PASSWORD PROTECTION
# ============================================================

def check_password():
    """Require a password before displaying the dashboard."""

    if st.session_state.get("authenticated", False):
        return True

    st.title("Sui-Unique Academy")
    st.subheader("Supervisor Review — Secure Access")

    password = st.text_input(
        "Enter your access password",
        type="password"
    )

    if st.button("Sign In"):
        if hmac.compare_digest(
            password,
            st.secrets["APP_PASSWORD"]
        ):
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("Incorrect password. Please try again.")

    return False


if not check_password():
    st.stop()


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


df = get_attendance()


# ============================================================
# SIDEBAR NAVIGATION
# ============================================================

st.sidebar.title("School Dashboard")

selected_page = st.sidebar.radio(
    "Choose a Section",
    [
        "Overview",
        "Student Attendance",
        "Early Warnings",
        "Student Follow-Ups"
    ]
)

st.sidebar.divider()
st.sidebar.caption(
    "Sui-Unique Academy | Research Prototype"
)

st.title("🎓 Sui-Unique Academy")
st.caption(
    "Student Attendance & Early Warning System — "
    "Research Prototype"
)


# ============================================================
# SECTION 1: OVERVIEW
# ============================================================

if selected_page == "Overview":

    st.header("Attendance Overview")

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
        df.groupby("Term")
        .agg(
            Students=("Student_ID", "nunique"),
            Attendance_Entries=("Student_ID", "size")
        )
        .reset_index()
    )

    st.dataframe(
        term_summary,
        hide_index=True,
        use_container_width=True
    )


# ============================================================
# SECTION 2: STUDENT ATTENDANCE
# ============================================================

elif selected_page == "Student Attendance":

    st.header("Student Attendance")

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
                [
                    f"{current_year-1}/{current_year}",
                    f"{current_year}/{current_year+1}",
                    f"{current_year+1}/{current_year+2}"
                ],
                index=1
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
            use_container_width=True
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
                df["Date"],
                errors="coerce"
            ).dt.date

            already_recorded = (
                df["Student_ID"]
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

    st.dataframe(
        filtered[
            [
                "Student_ID",
                "Class",
                "Term",
                "Week",
                "Date",
                "Arrival_Time",
                "Attendance_Status",
                "Minutes_Late"
            ]
        ],
        hide_index=True,
        use_container_width=True
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
                        "Term",
                        "Week",
                        "Arrival_Time",
                        "Attendance_Status",
                        "Minutes_Late"
                    ]
                ],
                hide_index=True,
                use_container_width=True
            )

    # --------------------------------------------------------
    # STUDENT ATTENDANCE LOOKUP
    # --------------------------------------------------------

    st.divider()

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
            use_container_width=True
        )


# ============================================================
# SECTION 3: EARLY WARNINGS
# ============================================================

elif selected_page == "Early Warnings":

    st.header("🔔 Early Warning & Attendance Support")

    st.write(
        "Review recorded lateness patterns "
        "and data completeness."
    )

    # --------------------------------------------------------
    # LOAD AI RISK RESULTS
    # --------------------------------------------------------

    risk_df = load_risk()

    latest_risk = (
        risk_df.sort_values("Prediction_Week")
        .groupby(
            ["Student_ID", "Term"],
            as_index=False
        )
        .tail(1)
        .copy()
    )

    warning_term = st.selectbox(
        "Select Term for Attendance Review",
        [
            "First Term",
            "Second Term",
            "Third Term"
        ]
    )

    term_risk = latest_risk[
        latest_risk["Term"] == warning_term
    ].copy()

    # Convert stored values to Boolean.

    for column in [
        "Previously_Persistent",
        "Historical_Coverage_Complete"
    ]:

        term_risk[column] = (
            term_risk[column]
            .astype(str)
            .str.lower()
            .eq("true")
        )

    # --------------------------------------------------------
    # DETERMINE ATTENDANCE SUPPORT PRIORITY
    # --------------------------------------------------------

    def review_status(row):

        if row["Previously_Persistent"]:
            return (
                "High Priority - Persistent Lateness"
            )

        if not row["Historical_Coverage_Complete"]:
            return (
                "Records Check - Incomplete Records"
            )

        if row["Late_Days_Last_4_Weeks"] >= 3:
            return (
                "Medium Priority - Repeated Lateness"
            )

        return "Routine Monitoring"

    term_risk["Review_Status"] = term_risk.apply(
        review_status,
        axis=1
    )

    # --------------------------------------------------------
    # EARLY WARNING SUMMARY
    # --------------------------------------------------------

    c1, c2, c3 = st.columns(3)

    c1.metric(
        "Medium Priority",
        int(
            (
                term_risk["Review_Status"]
                ==
                "Medium Priority - Repeated Lateness"
            ).sum()
        )
    )

    c2.metric(
        "High Priority",
        int(
            (
                term_risk["Review_Status"]
                ==
                "High Priority - Persistent Lateness"
            ).sum()
        )
    )

    c3.metric(
        "Records Check",
        int(
            (
                term_risk["Review_Status"]
                ==
                "Records Check - Incomplete Records"
            ).sum()
        )
    )

    # --------------------------------------------------------
    # STUDENTS FOR ATTENDANCE REVIEW
    # --------------------------------------------------------

    st.subheader("Students for Attendance Review")

    review_table = term_risk[
        [
            "Student_ID",
            "Class",
            "Prediction_Week",
            "Late_Days_Last_4_Weeks",
            "Exploratory_Risk_Score",
            "Review_Status"
        ]
    ].rename(
        columns={
            "Student_ID": "Student ID",
            "Prediction_Week": "Review Week",
            "Late_Days_Last_4_Weeks": (
                "Late Arrivals (4 Weeks)"
            ),
            "Review_Status": "Attendance Status"
        }
    )

    priority_filter = st.selectbox(
        "Filter Students by Priority",
        [
            "All Students",
            "High Priority",
            "Medium Priority",
            "Records Check",
            "Routine Monitoring"
        ]
    )

    filtered_review = review_table.copy()

    if priority_filter != "All Students":

        filtered_review = filtered_review[
            filtered_review["Attendance Status"]
            .str.startswith(
                priority_filter,
                na=False
            )
        ]

    student_filter = st.text_input(
        "Search by Student ID",
        placeholder="Example: SUA 001"
    )

    if student_filter.strip():

        filtered_review = filtered_review[
            filtered_review["Student ID"]
            .astype(str)
            .str.contains(
                student_filter.strip(),
                case=False,
                regex=False,
                na=False
            )
        ]

    st.write(
        "Students Displayed:",
        len(filtered_review)
    )

    display_review = filtered_review.rename(
        columns={
            "Exploratory_Risk_Score": (
                "AI Score (Experimental)"
            )
        }
    )

    display_review["AI Score (Experimental)"] = (
        pd.to_numeric(
            display_review["AI Score (Experimental)"],
            errors="coerce"
        ) * 100
    ).round(1)

    st.table(
        display_review.reset_index(
            drop=True
        ).style.format(
            {
                "AI Score (Experimental)": "{:.1f}"
            }
        )
    )

    # --------------------------------------------------------
    # INDIVIDUAL STUDENT AI REVIEW
    # --------------------------------------------------------

    st.divider()

    st.subheader("🔎 Individual Student AI Review")

    st.write(
        "Select a student to review attendance patterns "
        "and experimental AI results."
    )

    review_student = st.selectbox(
        "Select Student ID for AI Review",
        sorted(
            term_risk["Student_ID"]
            .dropna()
            .unique()
        ),
        key="individual_ai_student"
    )

    st.write(
        "Currently selected student:",
        review_student
    )

    student_ai = term_risk[
        term_risk["Student_ID"] == review_student
    ].iloc[0]

    a, b, c = st.columns(3)

    a.metric(
        "Recorded Late Arrivals (4 Weeks)",
        int(
            student_ai["Late_Days_Last_4_Weeks"]
        )
    )

    b.metric(
        "AI Score (Experimental)",
        (
            f'{float(student_ai["Exploratory_Risk_Score"]) * 100:.1f} / 100'
        )
    )

    c.metric(
        "Review Week",
        int(
            student_ai["Prediction_Week"]
        )
    )

    st.write(
        "**Attendance Support Priority:**",
        student_ai["Review_Status"]
    )

    # --------------------------------------------------------
    # INDIVIDUAL ATTENDANCE HISTORY
    # --------------------------------------------------------

    student_history = df[
        (
            df["Student_ID"]
            .astype(str)
            .str.strip()
            .str.upper()
            ==
            str(review_student)
            .strip()
            .upper()
        )
        &
        (
            df["Term"]
            .astype(str)
            .str.strip()
            .str.lower()
            ==
            str(warning_term)
            .strip()
            .lower()
        )
    ].copy()

    st.write(
        "Attendance records found for selected "
        "student and term:",
        len(student_history)
    )

    student_history = student_history.sort_values(
        "Date"
    )

    st.subheader("Student Attendance Summary")

    attendance_status = (
        student_history["Attendance_Status"]
        .astype(str)
        .str.strip()
        .str.lower()
    )

    late_days = (
        attendance_status == "late"
    ).sum()

    present_days = (
        attendance_status.isin(
            ["present", "on time"]
        )
    ).sum()

    absent_days = (
        attendance_status == "absent"
    ).sum()

    total_recorded = len(student_history)

    attendance_rate = (
        (
            (present_days + late_days)
            /
            total_recorded
        ) * 100
        if total_recorded > 0
        else 0
    )

    st.metric(
        "Recorded Attendance Rate",
        f"{attendance_rate:.1f}%"
    )

    col1, col2, col3, col4 = st.columns(4)

    col1.metric(
        "Late Days",
        int(late_days)
    )

    col2.metric(
        "Present (Not Marked Late)",
        int(present_days)
    )

    col3.metric(
        "Absent Days",
        int(absent_days)
    )

    col4.metric(
        "Total Recorded Days",
        len(student_history)
    )

    # --------------------------------------------------------
    # STUDENT ATTENDANCE HISTORY TABLE
    # --------------------------------------------------------

    st.subheader("Student Attendance History")

    student_history["Arrival_Time"] = (
        student_history["Arrival_Time"]
        .astype(str)
        .str.slice(0, 5)
    )

    st.dataframe(
        student_history[
            [
                "Date",
                "Week",
                "Arrival_Time",
                "Attendance_Status",
                "Minutes_Late"
            ]
        ],
        use_container_width=True,
        hide_index=True
    )

    # --------------------------------------------------------
    # WEEKLY LATENESS CHART
    # --------------------------------------------------------

    st.subheader("Weekly Lateness Pattern")

    weekly_lateness = student_history.copy()

    weekly_lateness["Is_Late"] = (
        weekly_lateness["Attendance_Status"]
        .astype(str)
        .str.strip()
        .str.lower()
        .eq("late")
    )

    weekly_lateness = (
        weekly_lateness.groupby("Week")["Is_Late"]
        .sum()
        .reset_index()
        .rename(
            columns={
                "Is_Late": "Late Arrivals"
            }
        )
        .sort_values("Week")
    )

    st.bar_chart(
        weekly_lateness.set_index(
            "Week"
        )["Late Arrivals"]
    )

    st.caption(
        "This table contains available attendance "
        "records for the selected student and term. "
        "Missing school days are not assumed punctual."
    )

    st.caption(
        "The AI score is exploratory and has not been "
        "validated as a probability of future lateness."
    )

    st.caption(
        "Based on available school records. "
        "Further Review is not a validated AI prediction."
    )

    # --------------------------------------------------------
    # PRIVATE PARENT WHATSAPP NOTIFICATION
    # TEST MODE
    # --------------------------------------------------------

    st.divider()

    st.subheader(
        "📱 Private Parent WhatsApp Notification"
    )

    st.info(
        "TEST MODE: Use only a WhatsApp number you own "
        "or have permission to test. Do not enter real "
        "parent contact details."
    )

    whatsapp_student = st.selectbox(
        "Select Student for Parent Notification",
        sorted(
            df["Student_ID"]
            .dropna()
            .astype(str)
            .unique()
        ),
        key="whatsapp_student_select"
    )

    st.write(
        "Selected Student:",
        whatsapp_student
    )

    test_phone = st.text_input(
        "Test WhatsApp Number",
        placeholder="08012345678",
        key="parent_whatsapp_test"
    )

    whatsapp_message = (
        "Good morning, Parent/Guardian.\n\n"
        "We would like to discuss your child's recent "
        "punctuality at school and understand whether "
        "there are any challenges we can help address.\n\n"
        "Kindly contact the class teacher at your convenience "
        "so we can work together to support your child.\n\n"
        "Thank you.\n"
        "Sui-Unique Academy"
    )

    edited_message = st.text_area(
        "Write or Edit Private WhatsApp Message",
        value=whatsapp_message,
        height=200,
        key="editable_parent_message"
    )

    if st.button(
        "Prepare Private WhatsApp Message"
    ):

        phone = "".join(
            c for c in test_phone
            if c.isdigit()
        )

        if (
            phone.startswith("0")
            and len(phone) == 11
        ):
            phone = "234" + phone[1:]

        if (
            not phone.startswith("234")
            or len(phone) != 13
        ):

            st.error(
                "Please enter a valid Nigerian "
                "WhatsApp number."
            )

        else:

            encoded_message = urllib.parse.quote(
                edited_message
            )

            whatsapp_link = (
                f"https://wa.me/{phone}"
                f"?text={encoded_message}"
            )

            st.success(
                "Private WhatsApp message prepared."
            )

            st.link_button(
                "📲 Open Private WhatsApp Chat",
                whatsapp_link
            )

            st.warning(
                "WhatsApp will open with the prepared "
                "message. It will NOT be sent automatically."
            )


# ============================================================
# SECTION 4: STUDENT FOLLOW-UPS
# ============================================================

elif selected_page == "Student Follow-Ups":

    st.header("📝 Student Support Follow-Up")

    st.write(
        "Record supportive actions to help students "
        "improve punctuality."
    )

    followup_file = Path(
        "data/real_school_data/"
        "student_support_followups.csv"
    )

    # --------------------------------------------------------
    # STUDENT FOLLOW-UP FORM
    # --------------------------------------------------------

    with st.form(
        "student_support_form",
        clear_on_submit=True
    ):

        followup_student = st.selectbox(
            "Student ID",
            sorted(
                df["Student_ID"]
                .dropna()
                .unique()
            )
        )

        followup_date = st.date_input(
            "Date of Follow-Up",
            value=date.today()
        )

        followup_action = st.selectbox(
            "Support Action",
            [
                "Parent or Guardian Contacted",
                "Student Counselling",
                "Transport Difficulty Discussed",
                "Attendance Monitoring",
                "Other Support"
            ]
        )

        followup_note = st.text_area(
            "Brief Note (Optional)"
        )

        submitted = st.form_submit_button(
            "Save Follow-Up"
        )

    # --------------------------------------------------------
    # SAVE FOLLOW-UP
    # --------------------------------------------------------

    if submitted:

        new_record = pd.DataFrame(
            [
                {
                    "Student_ID": followup_student,
                    "Follow_Up_Date": str(
                        followup_date
                    ),
                    "Support_Action": followup_action,
                    "Note": followup_note.strip()
                }
            ]
        )

        followup_file.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        new_record.to_csv(
            followup_file,
            mode="a",
            header=not followup_file.exists(),
            index=False
        )

        st.success(
            "Student support follow-up "
            "saved successfully."
        )

    # --------------------------------------------------------
    # DISPLAY RECORDED FOLLOW-UPS
    # --------------------------------------------------------

    st.subheader("Recorded Follow-Ups")

    if followup_file.exists():

        followup_data = pd.read_csv(
            followup_file
        )

        st.dataframe(
            followup_data,
            use_container_width=True,
            hide_index=True
        )

    else:

        st.info(
            "No follow-up actions have been "
            "recorded yet."
        )
