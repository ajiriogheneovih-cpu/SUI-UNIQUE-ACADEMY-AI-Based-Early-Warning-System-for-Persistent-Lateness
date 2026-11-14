import streamlit as st
import pandas as pd
from pathlib import Path
from datetime import date
import hmac

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

st.set_page_config(page_title="Sui-Unique Academy", page_icon="🎓", layout="wide")
if not check_password():
    st.stop()
DATA_DIR = Path("data/real_school_data")

@st.cache_data
def load_attendance():
    return pd.read_csv(DATA_DIR / "processed_school_attendance.csv")

@st.cache_data
def load_risk():
    return pd.read_csv(DATA_DIR / "school_ai_risk_scores_with_status.csv")

df = load_attendance()

st.sidebar.title("School Dashboard")
selected_page = st.sidebar.radio(
    "Choose a Section",
    ["Overview", "Student Attendance", "Early Warnings", "Student Follow-Ups"],
)
st.sidebar.divider()
st.sidebar.caption("Sui-Unique Academy | Research Prototype")

st.title("🎓 Sui-Unique Academy")
st.caption("Student Attendance & Early Warning System — Research Prototype")

if selected_page == "Overview":
    st.header("Attendance Overview")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Students in Records", df["Student_ID"].nunique())
    c2.metric("Attendance Records", len(df))
    c3.metric("Recorded Late Arrivals", int(df["Late_Calculated"].eq("Yes").sum()))
    c4.metric("Recorded Absences", int(df["Attendance_Status"].eq("Absent").sum()))
    st.info("Statistics reflect recorded attendance entries, not all scheduled school days.")
    st.subheader("Recorded Attendance by Term")
    st.dataframe(df.groupby("Term").agg(
        Students=("Student_ID", "nunique"),
        Attendance_Entries=("Student_ID", "size")
    ).reset_index(), hide_index=True, use_container_width=True)

elif selected_page == "Student Attendance":
    st.header("Student Attendance")
    term = st.selectbox("Select Term", ["All Terms"] + sorted(df["Term"].dropna().unique().tolist()))
    filtered = df if term == "All Terms" else df[df["Term"] == term]
    chosen_class = st.selectbox("Select Class", ["All Classes"] + sorted(filtered["Class"].dropna().unique().tolist()))
    if chosen_class != "All Classes":
        filtered = filtered[filtered["Class"] == chosen_class]
    st.dataframe(
        filtered[["Student_ID", "Class", "Term", "Week", "Date", "Arrival_Time",
                  "Attendance_Status", "Minutes_Late"]],
        hide_index=True, use_container_width=True
    )
    st.caption("Missing school days are not assumed punctual.")
    st.divider()
    st.subheader("🔎 Find a Student")
    search = st.text_input("Enter Student ID", placeholder="SUA 001")
    if search.strip():
        student = df[df["Student_ID"].astype(str).str.strip().str.upper() == search.strip().upper()].copy()
        if student.empty:
            st.warning("No student found with that ID.")
        else:
            student["Date"] = pd.to_datetime(student["Date"], errors="coerce")
            student = student.sort_values("Date")
            a, b, c = st.columns(3)
            a.metric("Recorded Days", len(student))
            b.metric("Late Arrivals", int(student["Late_Calculated"].eq("Yes").sum()))
            c.metric("Absences", int(student["Attendance_Status"].eq("Absent").sum()))
            st.dataframe(student[["Date", "Term", "Week", "Arrival_Time",
                                  "Attendance_Status", "Minutes_Late"]],
                         hide_index=True, use_container_width=True)
    st.divider()
    st.subheader("📋 Student Attendance Lookup")
    lookup_class = st.selectbox("1. Select Class", sorted(df["Class"].dropna().unique()), key="lookup_class")
    lookup_term = st.selectbox("2. Select Term", ["First Term", "Second Term", "Third Term"], key="lookup_term")
    matching = df[(df["Class"] == lookup_class) & (df["Term"] == lookup_term)]
    ids = sorted(matching["Student_ID"].dropna().unique())
    if not ids:
        st.warning("No student records found for this class and term.")
    else:
        sid = st.selectbox("3. Select Student ID", ids, key="lookup_student")
        student_data = matching[matching["Student_ID"] == sid]
        a, b, c = st.columns(3)
        a.metric("Recorded Days", len(student_data))
        b.metric("Late Arrivals", int(student_data["Late_Calculated"].eq("Yes").sum()))
        c.metric("Absences", int(student_data["Attendance_Status"].eq("Absent").sum()))
        st.dataframe(student_data[["Date", "Week", "Arrival_Time", "Attendance_Status",
                                   "Minutes_Late"]].sort_values("Date"),
                     hide_index=True, use_container_width=True)

elif selected_page == "Early Warnings":
    st.header("🔔 Early Warning & Attendance Support")

    st.write("Review recorded lateness patterns and data completeness.")

    # Load early warning records
    risk_df = pd.read_csv(
           "data/real_school_data/school_ai_risk_scores_with_status.csv"
    )

    
    # Select the latest available review week for each student
    latest_risk = (
        risk_df.sort_values("Prediction_Week")
        .groupby(["Student_ID", "Term"], as_index=False)
        .tail(1)
        .copy()
    )

    warning_term = st.selectbox(
        "Select Term for Attendance Review",
        ["First Term", "Second Term", "Third Term"]
    )

    term_risk = latest_risk[
        latest_risk["Term"] == warning_term
    ].copy()

    # Convert saved values into True/False
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

    
    def review_status(row):
        if row["Previously_Persistent"]:
            return "High Priority - Persistent Lateness"

        if not row["Historical_Coverage_Complete"]:
            return "Records Check - Incomplete Records"

        if row["Late_Days_Last_4_Weeks"] >= 3:
            return "Medium Priority - Repeated Lateness"

        return "Routine Monitoring"


    term_risk["Review_Status"] = term_risk.apply(
        review_status,
        axis=1
    )

    # Display summary cards
    
    c1, c2, c3 = st.columns(3)

    c1.metric(
        "Medium Priority",
        int(
            (term_risk["Review_Status"] ==
             "Medium Priority - Repeated Lateness").sum()
        )
    )

    c2.metric(
        "High Priority",
        int(
            (term_risk["Review_Status"] ==
             "High Priority - Persistent Lateness").sum()
        )
    )

    c3.metric(
        "Records Check",
        int(
            (term_risk["Review_Status"] ==
             "Records Check - Incomplete Records").sum()
        )
    )




    # Display student review table
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
            "Late_Days_Last_4_Weeks": "Late Arrivals (4 Weeks)",
            "Review_Status": "Attendance Status"
        }
    )

    # Filter students by attendance support priority
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
            filtered_review["Attendance Status"].str.startswith(
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
    st.write("Students Displayed:", len(filtered_review))

    display_review = filtered_review.rename(
        columns={
            "Exploratory_Risk_Score": "AI Score (Experimental)"
        }
    )

    display_review = filtered_review.rename(
        columns={
            "Exploratory_Risk_Score": "AI Score (Experimental)"
        }
    )

    # Convert experimental AI scores to a 0–100 scale
    display_review["AI Score (Experimental)"] = (
        pd.to_numeric(
            display_review["AI Score (Experimental)"],
            errors="coerce"
        ) * 100
    ).round(1)

    # Display the student review table
    st.table(
        display_review.reset_index(drop=True).style.format(
            {"AI Score (Experimental)": "{:.1f}"}
        )
    )

    st.divider()
    st.subheader("🔎 Individual Student AI Review")

    st.write(
        "Select a student to review attendance patterns "
        "and experimental AI results."
    )

    review_student = st.selectbox(
        "Select Student ID for AI Review",
        sorted(term_risk["Student_ID"].dropna().unique()),
        key="individual_ai_student"
    )
    st.write("Currently selected student:", review_student)
    student_ai = term_risk[
        term_risk["Student_ID"] == review_student
    ].iloc[0]

    a, b, c = st.columns(3)

    a.metric(
        "Recorded Late Arrivals (4 Weeks)",
        int(student_ai["Late_Days_Last_4_Weeks"])
    )

    b.metric(
        "AI Score (Experimental)",
        f'{float(student_ai["Exploratory_Risk_Score"]) * 100:.1f} / 100'
    )

    c.metric(
        "Review Week",
        int(student_ai["Prediction_Week"])
    )

    st.write(
        "**Attendance Support Priority:**",
        student_ai["Review_Status"]
    )

    
    student_history = df[
        (
            df["Student_ID"].astype(str).str.strip().str.upper()
            == str(review_student).strip().upper()
        )
        &
        (
            df["Term"].astype(str).str.strip().str.lower()
            == str(warning_term).strip().lower()
        )
    ].copy()

    st.write(
        "Attendance records found for selected student and term:",
        len(student_history)
    )


    student_history = student_history.sort_values("Date")

    st.subheader("Student Attendance Summary")

    attendance_status = (
        student_history["Attendance_Status"]
        .astype(str)
        .str.strip()
        .str.lower()
    )

    
    late_days = (attendance_status == "late").sum()

    present_days = (
        attendance_status.isin(["present", "on time"])
    ).sum()

    absent_days = (attendance_status == "absent").sum()

    total_recorded = len(student_history)

    attendance_rate = (
        ((present_days + late_days) / total_recorded) * 100
        if total_recorded > 0
        else 0
    )

    st.metric(
        "Recorded Attendance Rate",
        f"{attendance_rate:.1f}%"
    )


    col1, col2, col3, col4 = st.columns(4)

    col1.metric("Late Days", int(late_days))
    col2.metric("Present (Not Marked Late)", int(present_days))
    col3.metric("Absent Days", int(absent_days))
    col4.metric(
        "Total Recorded Days",
        len(student_history)
    )

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
        .rename(columns={"Is_Late": "Late Arrivals"})
        .sort_values("Week")
    )

    st.bar_chart(
        weekly_lateness.set_index("Week")["Late Arrivals"]
    )

    st.caption(
        "This table contains available attendance records "
        "for the selected student and term. "
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


elif selected_page == "Student Follow-Ups":
    st.header("📝 Student Support Follow-Up")
    st.write("Record supportive actions to help students improve punctuality.")

    from pathlib import Path
    from datetime import date

    followup_file = Path(
        "data/real_school_data/student_support_followups.csv"
    )



    with st.form("student_support_form", clear_on_submit=True):
        followup_student = st.selectbox(
            "Student ID",
            sorted(df["Student_ID"].dropna().unique())
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

        submitted = st.form_submit_button("Save Follow-Up")

    if submitted:
        new_record = pd.DataFrame([{
            "Student_ID": followup_student,
            "Follow_Up_Date": str(followup_date),
            "Support_Action": followup_action,
            "Note": followup_note.strip()
        }])

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

        st.success("Student support follow-up saved successfully.")

    st.subheader("Recorded Follow-Ups")

    if followup_file.exists():
        followup_data = pd.read_csv(followup_file)

        st.dataframe(
            followup_data,
            use_container_width=True,
            hide_index=True
        )
    else:
        st.info("No follow-up actions have been recorded yet.")
