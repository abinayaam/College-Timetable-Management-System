from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    send_file
)

from pymongo import MongoClient
import gridfs
from dotenv import load_dotenv
from bson.objectid import ObjectId
from pymongo.errors import DuplicateKeyError

import os
from datetime import datetime, timedelta
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.enums import TA_CENTER


# =========================================================
# LOAD ENVIRONMENT VARIABLES
# =========================================================

load_dotenv()


# =========================================================
# FLASK APP
# =========================================================

app = Flask(__name__)

app.secret_key = os.getenv("SECRET_KEY")


# =========================================================
# MONGODB CONNECTION
# =========================================================

mongo_uri = os.getenv("MONGO_URI")

client = MongoClient(mongo_uri)

db = client["college_timetable"]
# Faculty photo storage in MongoDB
faculty_fs = gridfs.GridFS(db, collection="faculty_photos")
def upload_faculty_photo(photo_path, faculty_key):
    with open(photo_path, "rb") as photo_file:
        photo_data = photo_file.read()

    existing = faculty_fs.find_one({
        "filename": faculty_key
    })

    if existing:
        faculty_fs.delete(existing._id)

    faculty_fs.put(
        photo_data,
        filename=faculty_key
    )
timetables = db["timetables"]
students = db["students"]
staff_collection = db["staff"]
saturday_bookings = db["saturday_bookings"]
notifications = db["notifications"]
announcements = db["announcements"]
# =========================================================
# SATURDAY BOOKING UNIQUE INDEX
# =========================================================

saturday_bookings.create_index(
    [
        ("booking_date", 1),
        ("period", 1)
    ],
    unique=True
)


# =========================================================
# LOGIN
# =========================================================

@app.route("/", methods=["GET", "POST"])
def home():

    if request.method == "POST":

        username = request.form["username"].strip()
        password = request.form["password"]
        role = request.form["role"]


        # =================================================
        # ADMIN LOGIN
        # =================================================

        if (
            role == "admin"
            and username == "admin"
            and password == "admin123"
        ):

            session["logged_in"] = True
            session["role"] = "admin"
            session["username"] = username

            return redirect(
                url_for("dashboard")
            )


        # =================================================
        # STAFF LOGIN
        # =================================================

        elif role == "staff":

            staff = staff_collection.find_one({
                "username": username,
                "password": password,
                "role": "staff"
            })

            if staff:

                session["logged_in"] = True
                session["role"] = "staff"
                session["username"] = staff["username"]
                session["staff_name"] = staff["name"]

                return redirect(
                    url_for("dashboard")
                )

            else:

                return render_template(
                    "login.html",
                    error="Invalid staff username or password"
                )


        # =================================================
        # STUDENT LOGIN
        # =================================================

        elif role == "student":

            student = students.find_one({
                "roll_number": username,
                "password": password,
                "role": "student"
            })

            if student:

                session["logged_in"] = True
                session["role"] = "student"
                session["username"] = student["roll_number"]
                session["student_name"] = student["name"]
                session["student_batch"] = student["batch"]
                session["student_year"] = student["year"]
                session["student_domain"] = student.get(
                    "domain",
                    ""
                )

                session["student_oec_courses"] = student.get(
                    "oec_courses",
                    []
                )

                password_changed = student.get(
                    "password_changed",
                    False
                )

                session["password_changed"] = password_changed


                # -----------------------------------------
                # FIRST LOGIN
                # -----------------------------------------

                if not password_changed:

                    return redirect(
                        url_for("change_password")
                    )


                # -----------------------------------------
                # NORMAL LOGIN
                # -----------------------------------------

                return redirect(
                    url_for("student")
                )


            else:

                return render_template(
                    "login.html",
                    error="Invalid student roll number or password"
                )


        # =================================================
        # INVALID ROLE
        # =================================================

        else:

            return render_template(
                "login.html",
                error="Invalid username, password or role"
            )


    return render_template("login.html")


# =========================================================
# ADMIN PAGE
# =========================================================

@app.route("/admin")
def admin():

    return render_template(
        "admin.html"
    )


# =========================================================
# ADD TIMETABLE
# =========================================================

@app.route("/add-timetable", methods=["GET", "POST"])
def add_timetable():

    if not session.get("logged_in"):

        return redirect(
            url_for("home")
        )


    if session.get("role") not in [
        "admin",
        "staff"
    ]:

        return redirect(
            url_for("dashboard")
        )


    if request.method == "POST":

        department = request.form.get(
            "department",
            ""
        ).strip()

        year = request.form.get(
            "year",
            ""
        ).strip()

        day = request.form.get(
            "day",
            ""
        ).strip()

        period = request.form.get(
            "period",
            ""
        ).strip()

        start_time = request.form.get(
            "start_time",
            ""
        ).strip()

        end_time = request.form.get(
            "end_time",
            ""
        ).strip()

        subject = request.form.get(
            "subject",
            ""
        ).strip()

        course_type = request.form.get(
            "course_type",
            ""
        ).strip()


        # =================================================
        # OEC
        # =================================================

        if course_type == "OEC":

            oec_courses = request.form.getlist(
                "oec_course[]"
            )

            oec_faculties = request.form.getlist(
                "oec_faculty[]"
            )

            oec_departments = request.form.getlist(
                "oec_department[]"
            )


            oec_data = []


            for i in range(
                len(oec_courses)
            ):

                if oec_courses[i].strip():

                    oec_data.append({

                        "course_name":
                            oec_courses[i].strip(),

                        "faculty":
                            oec_faculties[i].strip(),

                        "department":
                            oec_departments[i].strip()
                    })


            timetable = {

                "department":
                    department,

                "year":
                    year,

                "day":
                    day,

                "period":
                    period,

                "start_time":
                    start_time,

                "end_time":
                    end_time,

                "subject":
                    "OEC",

                "course_type":
                    "OEC",

                "oec_courses":
                    oec_data,

                "allocations":
                    []
            }


            timetables.insert_one(
                timetable
            )


            return redirect(
                url_for("view_timetable")
            )


        # =================================================
        # NORMAL / LAB
        # =================================================

        faculties = request.form.getlist(
            "faculty[]"
        )

        batches = request.form.getlist(
            "batch[]"
        )

        venues = request.form.getlist(
            "venue[]"
        )


        allocations = []


        for i in range(
            len(faculties)
        ):

            faculty = faculties[i].strip()


            batch_list = [

                batch.strip().upper()

                for batch in batches[i].split(",")

                if batch.strip()

            ]


            venue = ""


            if (
                course_type == "Lab"
                and i < len(venues)
            ):

                venue = venues[i].strip()


            allocations.append({

                "faculty":
                    faculty,

                "batches":
                    batch_list,

                "venue":
                    venue

            })


        timetable = {

            "department":
                department,

            "year":
                year,

            "day":
                day,

            "period":
                period,

            "start_time":
                start_time,

            "end_time":
                end_time,

            "subject":
                subject,

            "course_type":
                course_type,

            "allocations":
                allocations

        }


        timetables.insert_one(
            timetable
        )


        return redirect(
            url_for("view_timetable")
        )


    return render_template(
        "add_timetable.html"
    )


# =========================================================
# VIEW TIMETABLE
# =========================================================

@app.route("/view-timetable")
def view_timetable():

    search = request.args.get(
        "search",
        ""
    ).strip()

    day = request.args.get(
        "day",
        ""
    )

    batch = request.args.get(
        "batch",
        ""
    )

    department = request.args.get(
        "department",
        ""
    )


    query = {}


    # =====================================================
    # SEARCH
    # =====================================================

    if search:

        query["$or"] = [

            {
                "subject": {
                    "$regex": search,
                    "$options": "i"
                }
            },

            {
                "faculty": {
                    "$regex": search,
                    "$options": "i"
                }
            },

            {
                "venue": {
                    "$regex": search,
                    "$options": "i"
                }
            }

        ]


    # =====================================================
    # FILTERS
    # =====================================================

    if day:

        query["day"] = day


    if batch:

        query["batch"] = batch


    if department:

        query["department"] = department


    timetable_data = list(

        timetables.find(
            query
        ).sort(
            [
                ("day", 1),
                ("period", 1)
            ]
        )

    )


    return render_template(

        "timetable.html",

        timetables=timetable_data,

        search=search,

        selected_day=day,

        selected_batch=batch,

        selected_department=department

    )


# =========================================================
# EDIT TIMETABLE
# =========================================================

@app.route("/edit-timetable/<id>", methods=["GET", "POST"])
def edit_timetable(id):

    timetable = timetables.find_one({
        "_id": ObjectId(id)
    })

    if not timetable:
        return "Timetable not found", 404

    if request.method == "POST":

        old_period = timetable.get("period", "")
        old_subject = timetable.get("subject", "")
        old_day = timetable.get("day", "")

        new_period = request.form["period"]
        new_subject = request.form["subject"]
        new_day = request.form["day"]
        change_reason = request.form.get("change_reason", "").strip()

        updated_data = {
            "department": request.form["department"],
            "year": request.form["year"],
            "day": new_day,
            "period": new_period,
            "start_time": request.form["start_time"],
            "end_time": request.form["end_time"],
            "subject": new_subject,
            "course_type": request.form["course_type"]
        }

        timetables.update_one(
            {
                "_id": ObjectId(id)
            },
            {
                "$set": updated_data
            }
        )

        # ==========================================
        # CREATE NOTIFICATION FOR TIMETABLE CHANGE
        # ==========================================

        changes = []

        if old_period != new_period:
            changes.append(
                f"Period {old_period} → Period {new_period}"
            )

        if old_day != new_day:
            changes.append(
                f"Day {old_day} → {new_day}"
            )

        if old_subject != new_subject:
            changes.append(
                f"Subject {old_subject} → {new_subject}"
            )

        if changes:

            message = (
                f"{old_subject} timetable changed: "
                + ", ".join(changes)
            )

            notifications.insert_one({
    "subject": new_subject,
    "old_period": old_period,
    "new_period": new_period,
    "day": new_day,
    "message": message,
    "reason": change_reason,
    "created_at": datetime.now(),
    "read_by": []
})
        return redirect(
            url_for("view_timetable")
        )

    return render_template(
        "edit_timetable.html",
        timetable=timetable
    )

# =========================================================
# DELETE TIMETABLE
# =========================================================

@app.route("/delete-timetable/<id>")
def delete_timetable(id):

    timetables.delete_one({
        "_id": ObjectId(id)
    })


    return redirect(
        url_for("view_timetable")
    )


# =========================================================
# CHANGE PASSWORD
# =========================================================

@app.route(
    "/change-password",
    methods=["GET", "POST"]
)
def change_password():

    if not session.get("logged_in"):

        return redirect(
            url_for("home")
        )


    if session.get("role") != "student":

        return redirect(
            url_for("dashboard")
        )


    if request.method == "POST":

        current_password = request.form.get(
            "current_password",
            ""
        ).strip()

        new_password = request.form.get(
            "new_password",
            ""
        ).strip()

        confirm_password = request.form.get(
            "confirm_password",
            ""
        ).strip()


        student_roll = session.get(
            "username"
        )


        student = students.find_one({

            "roll_number":
                student_roll

        })


        if not student:

            return render_template(
                "change_password.html",
                error="Student account not found."
            )


        # =================================================
        # CURRENT PASSWORD CHECK
        # =================================================

        if student.get("password") != current_password:

            return render_template(
                "change_password.html",
                error="Current password is incorrect."
            )


        # =================================================
        # NEW PASSWORD CHECK
        # =================================================

        if not new_password:

            return render_template(
                "change_password.html",
                error="New password cannot be empty."
            )


        # =================================================
        # CONFIRM PASSWORD CHECK
        # =================================================

        if new_password != confirm_password:

            return render_template(
                "change_password.html",
                error="New password and confirm password do not match."
            )


        # =================================================
        # UPDATE PASSWORD
        # =================================================

        students.update_one(

            {
                "roll_number":
                    student_roll
            },

            {
                "$set": {

                    "password":
                        new_password,

                    "password_changed":
                        True

                }
            }

        )


        session["password_changed"] = True


        return redirect(
            url_for("student")
        )


    return render_template(
        "change_password.html"
    )


# =========================================================
# STUDENT TIMETABLE
# =========================================================

@app.route("/student")
def student():

    if not session.get("logged_in"):
        return redirect(url_for("home"))

    if session.get("role") != "student":
        return redirect(url_for("dashboard"))

    student_roll = session.get("username")

    student_batch = str(
        session.get("student_batch", "")
    ).strip().upper()

    student_year = str(
        session.get("student_year", "")
    ).strip()

    student_domain = str(
        session.get("student_domain", "")
    ).strip()

    student_record = students.find_one({
        "roll_number": student_roll
    })

    student_oec_courses = []

    if student_record:
        student_oec_courses = student_record.get(
            "oec_courses",
            []
        )

    timetable_data = list(
        timetables.find({
            "year": student_year,
            "department": "IT"
        })
    )

    final_timetables = []

    for timetable in timetable_data:

        allocations = timetable.get(
            "allocations",
            []
        )

        new_allocations = []

        for allocation in allocations:

            batches = [
                str(batch).strip().upper()
                for batch in allocation.get(
                    "batches",
                    []
                )
            ]

            if "ALL" in batches:

                updated_allocation = {
                    "faculty": allocation.get(
                        "faculty",
                        ""
                    ),
                    "batches": [student_batch],
                    "venue": allocation.get(
                        "venue",
                        ""
                    )
                }

                new_allocations.append(
                    updated_allocation
                )

            elif student_batch in batches:

                updated_allocation = {
                    "faculty": allocation.get(
                        "faculty",
                        ""
                    ),
                    "batches": batches,
                    "venue": allocation.get(
                        "venue",
                        ""
                    )
                }

                new_allocations.append(
                    updated_allocation
                )

        if (
            timetable.get(
                "course_type",
                ""
            ).strip().lower() == "oec"
        ):

            has_selected_oec = False

            for oec in timetable.get(
                "oec_courses",
                []
            ):

                if oec.get(
                    "course_name"
                ) in student_oec_courses:

                    has_selected_oec = True
                    break

            if has_selected_oec:

                timetable["allocations"] = []

                final_timetables.append(
                    timetable
                )

        elif new_allocations:

            timetable["allocations"] = (
                new_allocations
            )

            final_timetables.append(
                timetable
            )

    timetable_data = final_timetables

    search = request.args.get(
        "search",
        ""
    ).strip()

    if search:

        search_lower = search.lower()

        filtered_data = []

        for timetable in timetable_data:

            subject = str(
                timetable.get(
                    "subject",
                    ""
                )
            )

            if search_lower in subject.lower():

                filtered_data.append(
                    timetable
                )

                continue

            faculty_found = False

            for allocation in timetable.get(
                "allocations",
                []
            ):

                faculty = str(
                    allocation.get(
                        "faculty",
                        ""
                    )
                )

                if search_lower in faculty.lower():

                    filtered_data.append(
                        timetable
                    )

                    faculty_found = True

                    break

            if faculty_found:
                continue

            for oec in timetable.get(
                "oec_courses",
                []
            ):

                course_name = str(
                    oec.get(
                        "course_name",
                        ""
                    )
                )

                faculty = str(
                    oec.get(
                        "faculty",
                        ""
                    )
                )

                department = str(
                    oec.get(
                        "department",
                        ""
                    )
                )

                if (
                    search_lower
                    in course_name.lower()
                    or search_lower
                    in faculty.lower()
                    or search_lower
                    in department.lower()
                ):

                    filtered_data.append(
                        timetable
                    )

                    break

        timetable_data = filtered_data

    # ================= ANNOUNCEMENTS =================

    announcement_data = list(
        announcements.find().sort(
            "created_at",
            -1
        )
    )

    return render_template(
        "student.html",
        timetables=timetable_data,
        student_batch=student_batch,
        student_year=student_year,
        student_domain=student_domain,
        student_oec_courses=student_oec_courses,
        search=search,
        announcements=announcement_data
    )
@app.route("/ai-assistant")
def ai_assistant():

    if not session.get("logged_in"):
        return redirect(url_for("home"))

    if session.get("role") != "student":
        return redirect(url_for("dashboard"))

    question = request.args.get("question", "").strip()

    answer = "TEST ANSWER"

    student_batch = str(
        session.get("student_batch", "")
    ).strip().upper()

    if question:

        question_lower = question.lower()

        timetable_data = list(
            timetables.find({
                "department": "IT"
            })
        )

        print("AI TIMETABLE COUNT:", len(timetable_data))
        print("AI QUESTION:", question)

        found = []

        for timetable in timetable_data:

            subject = str(
                timetable.get("subject", "")
            ).strip()

            if subject and subject.lower() in question_lower:

                allocations = timetable.get(
                    "allocations",
                    []
                )

                for allocation in allocations:

                    batches = [
                        str(batch).strip().upper()
                        for batch in allocation.get(
                            "batches",
                            []
                        )
                    ]

                    if (
                        "ALL" in batches
                        or student_batch in batches
                    ):
                        found.append(timetable)
                        break

        if found:

            timetable = found[0]

            faculty_names = []

            for allocation in timetable.get(
                "allocations",
                []
            ):

                faculty = str(
                    allocation.get(
                        "faculty",
                        ""
                    )
                ).strip()

                if faculty:
                    faculty_names.append(faculty)

            faculty_text = ", ".join(
                faculty_names
            )

            answer = (
                f"{timetable.get('subject', '')} "
                f"is on {timetable.get('day', '')}, "
                f"Period {timetable.get('period', '')} "
                f"from {timetable.get('start_time', '')} "
                f"to {timetable.get('end_time', '')}."
            )

            if faculty_text:
                answer += (
                    f" Faculty: {faculty_text}."
                )

        else:

            answer = (
                "Sorry, I couldn't find that "
                "subject in your timetable."
            )

    return render_template(
        "ai_assistant.html",
        question=question,
        answer=answer
    )
# =========================================================
# TODAY
# =========================================================

@app.route("/today")
def today():

    search = request.args.get(
        "search",
        ""
    ).strip()

    batch = request.args.get(
        "batch",
        ""
    )


    today_day = datetime.now().strftime(
        "%A"
    )


    query = {

        "day":
            today_day

    }


    # =====================================================
    # SEARCH
    # =====================================================

    if search:

        query["$or"] = [

            {
                "subject": {
                    "$regex": search,
                    "$options": "i"
                }
            },

            {
                "faculty": {
                    "$regex": search,
                    "$options": "i"
                }
            },

            {
                "venue": {
                    "$regex": search,
                    "$options": "i"
                }
            }

        ]


    # =====================================================
    # BATCH FILTER
    # =====================================================

    if batch:

        query["batch"] = batch


    timetable_data = list(

        timetables.find(
            query
        ).sort(
            "start_time",
            1
        )

    )


    # =====================================================
    # FIND NEXT CLASS
    # =====================================================

    current_time = datetime.now().time()

    next_class = None


    for item in timetable_data:

        try:

            class_time = datetime.strptime(

                item["start_time"],

                "%H:%M"

            ).time()


            if class_time > current_time:

                next_class = item

                break


        except (
            ValueError,
            KeyError
        ):

            continue


    return render_template(

        "today.html",

        timetables=timetable_data,

        today_day=today_day,

        next_class=next_class,

        search=search,

        selected_batch=batch

    )


# =========================================================
# DASHBOARD
# =========================================================

@app.route("/dashboard")
def dashboard():

    if not session.get("logged_in"):

        return redirect(
            url_for("home")
        )


    total_timetables = \
        timetables.count_documents({})


    today_day = datetime.now().strftime(
        "%A"
    )


    today_classes = timetables.count_documents({

        "day":
            today_day

    })


    return render_template(

        "dashboard.html",

        role=
            session.get("role"),

        username=
            session.get("username"),

        total_timetables=
            total_timetables,

        today_classes=
            today_classes,

        today_day=
            today_day

    )


# =========================================================
# SATURDAY BOOKING
# =========================================================

@app.route(
    "/saturday-booking",
    methods=["GET", "POST"]
)
def saturday_booking():

    if not session.get("logged_in"):

        return redirect(
            url_for("home")
        )


    if session.get("role") != "staff":

        return redirect(
            url_for("dashboard")
        )


    now = datetime.now()


    # =====================================================
    # FIND UPCOMING SATURDAY
    # =====================================================

    days_until_saturday = (
        5 - now.weekday()
    ) % 7


    saturday_date = (
        now.date()
        + timedelta(
            days=days_until_saturday
        )
    )


    # Thursday of the same week
    thursday_date = (
        saturday_date
        - timedelta(days=2)
    )


    # =====================================================
    # BOOKING START
    # THURSDAY 12:00 AM
    # =====================================================

    booking_start = datetime(

        thursday_date.year,
        thursday_date.month,
        thursday_date.day,

        0,
        0,
        0

    )


    # =====================================================
    # BOOKING END
    # SATURDAY 11:59 PM
    # =====================================================

    booking_end = datetime(

        saturday_date.year,
        saturday_date.month,
        saturday_date.day,

        23,
        59,
        59

    )


    # =====================================================
    # BOOKING OPEN / CLOSED
    # =====================================================

    booking_open = (

        booking_start
        <= now
        <= booking_end

    )


    # =====================================================
    # GET BOOKED PERIODS
    # =====================================================

    booked_slots = list(

        saturday_bookings.find({

            "booking_date":
                saturday_date.isoformat()

        }).sort(
            "period",
            1
        )

    )


    booked_periods = {

        booking["period"]

        for booking in booked_slots

    }


    error = None


    # =====================================================
    # HANDLE BOOKING
    # =====================================================

    if request.method == "POST":

        if not booking_open:

            error = (
                "Saturday booking is closed."
            )


        else:

            period = request.form[
                "period"
            ]

            subject = request.form[
                "subject"
            ].strip()


            booking = {

                "booking_date":
                    saturday_date.isoformat(),

                "day":
                    "Saturday",

                "period":
                    period,

                "subject":
                    subject,

                "staff_username":
                    session.get("username"),

                "staff_name":
                    session.get("staff_name"),

                "department":
                    "IT",

                "status":
                    "booked",

                "booked_at":
                    now.strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )

            }


            try:

                saturday_bookings.insert_one(
                    booking
                )


                return redirect(
                    url_for(
                        "saturday_booking"
                    )
                )


            except DuplicateKeyError:

                error = (
                    "This period has already been "
                    "booked by another staff member."
                )


                booked_slots = list(

                    saturday_bookings.find({

                        "booking_date":
                            saturday_date.isoformat()

                    }).sort(
                        "period",
                        1
                    )

                )


                booked_periods = {

                    booking["period"]

                    for booking
                    in booked_slots

                }


    return render_template(

        "saturday_booking.html",

        booking_open=
            booking_open,

        saturday_date=
            saturday_date,

        deadline=
            booking_end,

        booked_slots=
            booked_slots,

        booked_periods=
            booked_periods,

        error=
            error

    )
# =========================================================
# DOWNLOAD STUDENT TIMETABLE AS PDF
# =========================================================

@app.route("/download-timetable")
def download_timetable():

    if not session.get("logged_in"):
        return redirect(url_for("home"))

    if session.get("role") != "student":
        return redirect(url_for("dashboard"))

    student_roll = session.get("username")
    student_batch = str(
        session.get("student_batch", "")
    ).strip().upper()

    student_year = str(
        session.get("student_year", "")
    ).strip()

    student_domain = str(
        session.get("student_domain", "")
    ).strip()

    student_record = students.find_one({
        "roll_number": student_roll
    })

    student_name = "Student"

    if student_record:
        student_name = student_record.get(
            "name",
            "Student"
        )

    # -----------------------------------------------------
    # GET STUDENT TIMETABLE
    # -----------------------------------------------------

    timetable_data = list(
        timetables.find({
            "year": student_year,
            "department": "IT"
        }).sort([
            ("day", 1),
            ("start_time", 1)
        ])
    )

    # -----------------------------------------------------
    # FILTER FOR STUDENT
    # -----------------------------------------------------

    final_timetables = []

    student_oec_courses = []

    if student_record:
        student_oec_courses = student_record.get(
            "oec_courses",
            []
        )

    for timetable in timetable_data:

        course_type = str(
            timetable.get(
                "course_type",
                ""
            )
        ).strip().lower()

        # OEC
        if course_type == "oec":

            selected_oec = []

            for oec in timetable.get(
                "oec_courses",
                []
            ):

                if oec.get(
                    "course_name"
                ) in student_oec_courses:

                    selected_oec.append(oec)

            if selected_oec:
                timetable["selected_oec"] = selected_oec
                final_timetables.append(timetable)

            continue

        # NORMAL / LAB
        matched_allocations = []

        for allocation in timetable.get(
            "allocations",
            []
        ):

            batches = [
                str(batch).strip().upper()
                for batch in allocation.get(
                    "batches",
                    []
                )
            ]

            if (
                "ALL" in batches
                or student_batch in batches
            ):

                matched_allocations.append(
                    allocation
                )

        if matched_allocations:

            timetable["student_allocations"] = \
                matched_allocations

            final_timetables.append(
                timetable
            )

    # -----------------------------------------------------
    # PDF FILE
    # -----------------------------------------------------

    file_name = (
        f"{student_roll}_timetable.pdf"
    )

    file_path = os.path.join(
        os.getcwd(),
        file_name
    )

    document = SimpleDocTemplate(
        file_path,
        pagesize=landscape(A4),
        rightMargin=20,
        leftMargin=20,
        topMargin=20,
        bottomMargin=20
    )

    styles = getSampleStyleSheet()

    title_style = styles["Title"]
    title_style.alignment = TA_CENTER

    story = []

    # -----------------------------------------------------
    # TITLE
    # -----------------------------------------------------

    story.append(
        Paragraph(
            "College Timetable",
            title_style
        )
    )

    story.append(
        Spacer(1, 10)
    )

    # -----------------------------------------------------
    # STUDENT DETAILS
    # -----------------------------------------------------

    student_details = [

        [
            "Name",
            student_name,
            "Roll No",
            student_roll
        ],

        [
            "Batch",
            student_batch,
            "Year",
            student_year
        ],

        [
            "Domain",
            student_domain or "-",
            "",
            ""
        ]

    ]

    details_table = Table(
        student_details,
        colWidths=[
            70,
            180,
            70,
            180
        ]
    )

    details_table.setStyle(
        TableStyle([

            (
                "GRID",
                (0, 0),
                (-1, -1),
                0.5,
                colors.grey
            ),

            (
                "FONTNAME",
                (0, 0),
                (0, -1),
                "Helvetica-Bold"
            ),

            (
                "FONTNAME",
                (2, 0),
                (2, -2),
                "Helvetica-Bold"
            ),

            (
                "VALIGN",
                (0, 0),
                (-1, -1),
                "MIDDLE"
            ),

            (
                "BOTTOMPADDING",
                (0, 0),
                (-1, -1),
                7
            ),

            (
                "TOPPADDING",
                (0, 0),
                (-1, -1),
                7
            )

        ])
    )

    story.append(details_table)

    story.append(
        Spacer(1, 15)
    )

    # -----------------------------------------------------
    # TIMETABLE HEADER
    # -----------------------------------------------------

    periods = [
        "I",
        "II",
        "III",
        "IV",
        "V",
        "VI",
        "VII",
        "VIII"
    ]

    period_times = {

        "I": "09:15 - 10:05",
        "II": "10:05 - 10:55",
        "III": "11:10 - 12:00",
        "IV": "12:00 - 12:50",
        "V": "01:50 - 02:40",
        "VI": "02:40 - 03:30",
        "VII": "03:40 - 04:30",
        "VIII": "04:30 - 05:15"

    }

    days = [
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday"
    ]

    pdf_data = []

    header = [
        Paragraph(
            "<b>Day</b>",
            styles["Normal"]
        )
    ]

    for period in periods:

        header.append(
            Paragraph(
                f"<b>Period {period}</b><br/>"
                f"{period_times[period]}",
                styles["Normal"]
            )
        )

    pdf_data.append(header)

    # -----------------------------------------------------
    # CREATE EACH DAY
    # -----------------------------------------------------

    for day in days:

        row = [
            Paragraph(
                f"<b>{day[:3].upper()}</b>",
                styles["Normal"]
            )
        ]

        day_items = [
            item
            for item in final_timetables
            if item.get("day") == day
        ]

        used_periods = set()

        for period in periods:

            if period in used_periods:
                continue

            matching_item = None

            for item in day_items:

                raw_period = str(
                    item.get(
                        "period",
                        ""
                    )
                ).upper().strip()

                if raw_period == period:

                    matching_item = item
                    break

                if (
                    period == "V"
                    and raw_period in [
                        "V-VI",
                        "5-6"
                    ]
                    and str(
                        item.get(
                            "course_type",
                            ""
                        )
                    ).lower() == "lab"
                ):

                    matching_item = item
                    break

                if (
                    period == "VII"
                    and raw_period in [
                        "VII-VIII",
                        "7-8"
                    ]
                    and str(
                        item.get(
                            "course_type",
                            ""
                        )
                    ).lower() == "lab"
                ):

                    matching_item = item
                    break

            # -------------------------------------------------
            # EMPTY
            # -------------------------------------------------

            if not matching_item:

                row.append("-")
                continue

            # -------------------------------------------------
            # OEC
            # -------------------------------------------------

            if str(
                matching_item.get(
                    "course_type",
                    ""
                )
            ).lower() == "oec":

                oec_text = "<b>OEC</b>"

                for oec in matching_item.get(
                    "selected_oec",
                    []
                ):

                    oec_text += (
                        f"<br/>{oec.get('course_name', '-')}"
                        f"<br/>Faculty: {oec.get('faculty', '-')}"
                        f"<br/>Dept: {oec.get('department', '-')}"
                    )

                row.append(
                    Paragraph(
                        oec_text,
                        styles["Normal"]
                    )
                )

            # -------------------------------------------------
            # NORMAL / LAB
            # -------------------------------------------------

            else:

                subject = matching_item.get(
                    "subject",
                    "-"
                )

                cell_text = (
                    f"<b>{subject}</b>"
                )

                faculty_list = []

                venue_list = []

                for allocation in matching_item.get(
                    "student_allocations",
                    []
                ):

                    if allocation.get("faculty"):
                        faculty_list.append(
                            allocation.get("faculty")
                        )

                    if allocation.get("venue"):
                        venue_list.append(
                            allocation.get("venue")
                        )

                if faculty_list:

                    cell_text += (
                        "<br/>Faculty: "
                        + " / ".join(
                            dict.fromkeys(
                                faculty_list
                            )
                        )
                    )

                cell_text += (
                    f"<br/>Batch: {student_batch}"
                )

                if venue_list:

                    cell_text += (
                        "<br/>Venue: "
                        + " / ".join(
                            dict.fromkeys(
                                venue_list
                            )
                        )
                    )

                if str(
                    matching_item.get(
                        "course_type",
                        ""
                    )
                ).lower() == "lab":

                    cell_text += (
                        "<br/><b>LAB</b>"
                    )

                row.append(
                    Paragraph(
                        cell_text,
                        styles["Normal"]
                    )
                )

                # Merge V-VI
                raw_period = str(
                    matching_item.get(
                        "period",
                        ""
                    )
                ).upper().strip()

                if raw_period in [
                    "V-VI",
                    "5-6"
                ]:

                    used_periods.add("VI")

                # Merge VII-VIII
                if raw_period in [
                    "VII-VIII",
                    "7-8"
                ]:

                    used_periods.add("VIII")

        pdf_data.append(row)

    # -----------------------------------------------------
    # TABLE
    # -----------------------------------------------------

    timetable_table = Table(
        pdf_data,
        colWidths=[
            45,
            85,
            85,
            85,
            85,
            85,
            85,
            85,
            85
        ]
    )

    timetable_table.setStyle(
        TableStyle([

            (
                "GRID",
                (0, 0),
                (-1, -1),
                0.5,
                colors.grey
            ),

            (
                "BACKGROUND",
                (0, 0),
                (-1, 0),
                colors.lightgrey
            ),

            (
                "ALIGN",
                (0, 0),
                (-1, -1),
                "CENTER"
            ),

            (
                "VALIGN",
                (0, 0),
                (-1, -1),
                "MIDDLE"
            ),

            (
                "TOPPADDING",
                (0, 0),
                (-1, -1),
                8
            ),

            (
                "BOTTOMPADDING",
                (0, 0),
                (-1, -1),
                8
            )

        ])
    )

    story.append(
        timetable_table
    )

    # -----------------------------------------------------
    # BUILD PDF
    # -----------------------------------------------------

    document.build(
        story
    )

    return send_file(
        file_path,
        as_attachment=True,
        download_name=file_name
    )
# =========================================================
# STUDENT NOTIFICATIONS
# =========================================================

@app.route("/notifications")
def notifications_page():

    if not session.get("logged_in"):
        return redirect(url_for("home"))

    if session.get("role") != "student":
        return redirect(url_for("dashboard"))

    notification_data = list(
        notifications.find().sort(
            "created_at",
            -1
        )
    )

    return render_template(
        "notifications.html",
        notifications=notification_data
    )
@app.route("/staff-announcement", methods=["GET", "POST"])
def staff_announcement():

    if not session.get("logged_in"):
        return redirect(url_for("home"))

    if session.get("role") != "staff":
        return redirect(url_for("dashboard"))

    if request.method == "POST":

        title = request.form["title"].strip()
        message = request.form["message"].strip()
        target = request.form["target"].strip()

        announcements.insert_one({
            "title": title,
            "message": message,
            "target": target,
            "created_at": datetime.now(),
            "created_by": session.get("staff_name", "")
        })

        return redirect(
            url_for("staff_announcement")
        )

    return render_template(
        "staff_announcement.html"
    )

# =========================================================
# LOGOUT
# =========================================================

@app.route("/logout")
def logout():

    session.clear()

    return redirect(
        url_for("home")
    )

if __name__ == "__main__":

    upload_faculty_photo(
        r"C:\CollegeTimetable\static\faculty_photos\ai_faculty.jpg",
        "ai_faculty.jpg"
    )

    upload_faculty_photo(
        r"C:\CollegeTimetable\static\faculty_photos\mwt_faculty.jpg",
        "mwt_faculty.jpg"
    )

    app.run(
        debug=True
    )
# =========================================================
# RUN APP
# =========================================================

if __name__ == "__main__":

    app.run(
        debug=True
    )