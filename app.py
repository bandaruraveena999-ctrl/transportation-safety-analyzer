import streamlit as st
import pandas as pd
import geopandas as gpd
import folium

from folium.plugins import Draw, MeasureControl, MiniMap
from overturemaps import core


# ---------------------------------------------------------
# PAGE CONFIG
# ---------------------------------------------------------

st.set_page_config(
    layout="wide",
    page_title="High Injury Network Analyzer"
)

st.title("High Injury Network Analyzer")


# ---------------------------------------------------------
# ROAD NETWORK DOWNLOAD - OVERTURE MAPS
# ---------------------------------------------------------

@st.cache_data(ttl=3600, max_entries=1)
def get_road_network(west, south, east, north):
    try:
        bbox = (
            west,
            south,
            east,
            north
        )

        roads = core.geodataframe(
            "segment",
            bbox=bbox
        )

        if roads is None or roads.empty:
            return None

        # Keep road segments only
        if "subtype" in roads.columns:
            roads = roads[
                roads["subtype"] == "road"
            ].copy()

        if roads.empty:
            return None

        # Remove invalid geometries
        roads = roads[
            roads.geometry.notna()
        ].copy()

        if roads.empty:
            return None

        # Create road segment ID
        roads["segment_id"] = (
            roads["id"].astype(str)
        )

        # Keep only columns required for HIN
        roads = roads[
            [
                "segment_id",
                "geometry"
            ]
        ].copy()

        if roads.crs is None:
            roads = roads.set_crs(
                "EPSG:4326"
            )

        return roads

    except Exception as e:
        st.error(
            f"Road network download failed: {e}"
        )
        return None


# ---------------------------------------------------------
# SESSION STATE
# ---------------------------------------------------------

session_keys = [
    "hin_csv",
    "hin_count",
    "hin_edges",
    "ksi",
    "lat_col",
    "lon_col",
    "death_col",
    "show_hin",
    "show_crashes",
    "basemap"
]

for key in session_keys:
    if key not in st.session_state:
        st.session_state[key] = None

if "hin_done" not in st.session_state:
    st.session_state.hin_done = False


# ---------------------------------------------------------
# SIDEBAR
# ---------------------------------------------------------

with st.sidebar:
    st.header("Controls")

    uploaded_file = st.file_uploader(
        "Upload crash data",
        type=["csv", "zip"],
        help="Upload a CSV file or ZIP file containing one CSV."
    )

    if uploaded_file is not None:

        # -------------------------------------------------
        # READ ONLY COLUMN NAMES FIRST
        # -------------------------------------------------

        try:
            uploaded_file.seek(0)

            if uploaded_file.name.lower().endswith(".zip"):
                header_df = pd.read_csv(
                    uploaded_file,
                    compression="zip",
                    nrows=0
                )
            else:
                header_df = pd.read_csv(
                    uploaded_file,
                    nrows=0
                )

            columns = list(
                header_df.columns
            )

            st.success(
                "Crash file uploaded successfully"
            )

        except Exception as e:
            st.error(
                f"Unable to read uploaded file: {e}"
            )
            st.stop()


        # -------------------------------------------------
        # COLUMN SELECTION
        # -------------------------------------------------

        st.subheader(
            "Map Columns"
        )

        st.caption(
            "Required fields"
        )

        lat_col = st.selectbox(
            "Latitude column",
            columns
        )

        lon_col = st.selectbox(
            "Longitude column",
            columns
        )

        death_col = st.selectbox(
            "Death count column",
            columns
        )

        injury_col = st.selectbox(
            "Serious injury column",
            columns
        )


        # -------------------------------------------------
        # OPTIONAL FILTERS
        # -------------------------------------------------

        st.subheader(
            "Optional Filters"
        )

        st.caption(
            "Leave as None if the field is not available."
        )

        optional_cols = (
            ["None"]
            + columns
        )

        ped_death_col = st.selectbox(
            "Pedestrian death column",
            optional_cols
        )

        ped_injury_col = st.selectbox(
            "Pedestrian injury column",
            optional_cols
        )

        bike_death_col = st.selectbox(
            "Bike death column",
            optional_cols
        )

        bike_injury_col = st.selectbox(
            "Bike injury column",
            optional_cols
        )


        # -------------------------------------------------
        # HIN MODE
        # -------------------------------------------------

        st.subheader(
            "HIN Mode"
        )

        hin_mode = st.radio(
            "Generate HIN for:",
            [
                "All KSI crashes",
                "Pedestrian crashes only",
                "Bike crashes only",
                "Pedestrian + Bike only"
            ]
        )


        # -------------------------------------------------
        # HIN SETTINGS
        # -------------------------------------------------

        st.subheader(
            "HIN Settings"
        )

        hin_threshold = st.slider(
            "Minimum KSI crashes for HIN",
            min_value=1,
            max_value=10,
            value=2
        )


        # -------------------------------------------------
        # MAP DISPLAY
        # -------------------------------------------------

        st.subheader(
            "Map Display"
        )

        show_crashes = st.checkbox(
            "Show crash points",
            value=True
        )

        show_hin = st.checkbox(
            "Show HIN segments",
            value=True
        )

        basemap = st.selectbox(
            "Basemap",
            [
                "CartoDB dark_matter",
                "CartoDB positron",
                "OpenStreetMap"
            ]
        )


        # -------------------------------------------------
        # GENERATE
        # -------------------------------------------------

        generate = st.button(
            "Generate HIN",
            type="primary"
        )


        if generate:

            st.session_state.hin_done = False

            st.session_state.show_hin = (
                show_hin
            )

            st.session_state.show_crashes = (
                show_crashes
            )

            st.session_state.basemap = (
                basemap
            )


            # -------------------------------------------------
            # LOAD ONLY REQUIRED COLUMNS
            # -------------------------------------------------

            required_cols = [
                lat_col,
                lon_col,
                death_col,
                injury_col
            ]

            for col in [
                ped_death_col,
                ped_injury_col,
                bike_death_col,
                bike_injury_col
            ]:
                if (
                    col != "None"
                    and
                    col not in required_cols
                ):
                    required_cols.append(
                        col
                    )


            try:
                uploaded_file.seek(0)

                with st.spinner(
                    "Loading required crash fields..."
                ):

                    if uploaded_file.name.lower().endswith(".zip"):
                        df = pd.read_csv(
                            uploaded_file,
                            compression="zip",
                            usecols=required_cols,
                            low_memory=False
                        )
                    else:
                        df = pd.read_csv(
                            uploaded_file,
                            usecols=required_cols,
                            low_memory=False
                        )

                st.write(
                    f"Processing {len(df):,} crash records"
                )

            except Exception as e:
                st.error(
                    f"Unable to load crash data: {e}"
                )
                st.stop()


            # -------------------------------------------------
            # CLEAN DATA
            # -------------------------------------------------

            with st.spinner(
                "Cleaning crash data..."
            ):

                df[lat_col] = pd.to_numeric(
                    df[lat_col],
                    errors="coerce"
                )

                df[lon_col] = pd.to_numeric(
                    df[lon_col],
                    errors="coerce"
                )

                df = df.dropna(
                    subset=[
                        lat_col,
                        lon_col
                    ]
                )

                df = df[
                    df[lat_col].between(
                        -90,
                        90
                    )
                    &
                    df[lon_col].between(
                        -180,
                        180
                    )
                    &
                    (df[lat_col] != 0)
                    &
                    (df[lon_col] != 0)
                ]

                df[death_col] = pd.to_numeric(
                    df[death_col],
                    errors="coerce"
                ).fillna(0)

                df[injury_col] = pd.to_numeric(
                    df[injury_col],
                    errors="coerce"
                ).fillna(0)

                all_ksi = df[
                    (df[death_col] > 0)
                    |
                    (df[injury_col] > 0)
                ]

                del df


            if all_ksi.empty:
                st.warning(
                    "No KSI crashes were found."
                )
                st.stop()


            # -------------------------------------------------
            # HIN MODE FILTERING
            # -------------------------------------------------

            if hin_mode == "All KSI crashes":

                ksi = all_ksi


            elif hin_mode == "Pedestrian crashes only":

                if (
                    ped_death_col == "None"
                    and
                    ped_injury_col == "None"
                ):
                    st.warning(
                        "Select at least one pedestrian field."
                    )
                    st.stop()

                ped_filter = pd.Series(
                    False,
                    index=all_ksi.index
                )

                if ped_death_col != "None":

                    all_ksi[ped_death_col] = pd.to_numeric(
                        all_ksi[ped_death_col],
                        errors="coerce"
                    ).fillna(0)

                    ped_filter = (
                        ped_filter
                        |
                        (
                            all_ksi[ped_death_col]
                            > 0
                        )
                    )

                if ped_injury_col != "None":

                    all_ksi[ped_injury_col] = pd.to_numeric(
                        all_ksi[ped_injury_col],
                        errors="coerce"
                    ).fillna(0)

                    ped_filter = (
                        ped_filter
                        |
                        (
                            all_ksi[ped_injury_col]
                            > 0
                        )
                    )

                ksi = all_ksi[
                    ped_filter
                ]


            elif hin_mode == "Bike crashes only":

                if (
                    bike_death_col == "None"
                    and
                    bike_injury_col == "None"
                ):
                    st.warning(
                        "Select at least one bike field."
                    )
                    st.stop()

                bike_filter = pd.Series(
                    False,
                    index=all_ksi.index
                )

                if bike_death_col != "None":

                    all_ksi[bike_death_col] = pd.to_numeric(
                        all_ksi[bike_death_col],
                        errors="coerce"
                    ).fillna(0)

                    bike_filter = (
                        bike_filter
                        |
                        (
                            all_ksi[bike_death_col]
                            > 0
                        )
                    )

                if bike_injury_col != "None":

                    all_ksi[bike_injury_col] = pd.to_numeric(
                        all_ksi[bike_injury_col],
                        errors="coerce"
                    ).fillna(0)

                    bike_filter = (
                        bike_filter
                        |
                        (
                            all_ksi[bike_injury_col]
                            > 0
                        )
                    )

                ksi = all_ksi[
                    bike_filter
                ]


            else:

                selected_cols = [
                    ped_death_col,
                    ped_injury_col,
                    bike_death_col,
                    bike_injury_col
                ]

                if all(
                    col == "None"
                    for col in selected_cols
                ):
                    st.warning(
                        "Select at least one pedestrian or bike field."
                    )
                    st.stop()

                combined_filter = pd.Series(
                    False,
                    index=all_ksi.index
                )

                for col in selected_cols:

                    if col != "None":

                        all_ksi[col] = pd.to_numeric(
                            all_ksi[col],
                            errors="coerce"
                        ).fillna(0)

                        combined_filter = (
                            combined_filter
                            |
                            (
                                all_ksi[col]
                                > 0
                            )
                        )

                ksi = all_ksi[
                    combined_filter
                ]


            if ksi.empty:
                st.warning(
                    "No crashes match the selected HIN mode."
                )
                st.stop()


            del all_ksi


            st.write(
                f"KSI crashes selected: {len(ksi):,}"
            )


            # -------------------------------------------------
            # STUDY AREA
            # -------------------------------------------------

            buffer = 0.01

            south = (
                float(
                    ksi[lat_col].min()
                )
                - buffer
            )

            north = (
                float(
                    ksi[lat_col].max()
                )
                + buffer
            )

            west = (
                float(
                    ksi[lon_col].min()
                )
                - buffer
            )

            east = (
                float(
                    ksi[lon_col].max()
                )
                + buffer
            )

            lat_span = (
                north
                - south
            )

            lon_span = (
                east
                - west
            )


            if (
                lat_span > 2.0
                or
                lon_span > 2.0
            ):
                st.error(
                    "Crash records span a very large geographic area. "
                    "Filter the dataset to one city or study region."
                )
                st.stop()


            # -------------------------------------------------
            # ROAD NETWORK
            # -------------------------------------------------

            with st.spinner(
                "Downloading road network from Overture Maps..."
            ):

                edges = get_road_network(
                    west,
                    south,
                    east,
                    north
                )


            if (
                edges is None
                or
                edges.empty
            ):
                st.error(
                    "Could not retrieve road network data."
                )
                st.stop()


            st.success(
                f"Loaded {len(edges):,} road segments"
            )


            # -------------------------------------------------
            # SPATIAL DATA
            # -------------------------------------------------

            with st.spinner(
                "Preparing spatial data..."
            ):

                ksi_gdf = gpd.GeoDataFrame(
                    ksi,
                    geometry=gpd.points_from_xy(
                        ksi[lon_col],
                        ksi[lat_col]
                    ),
                    crs="EPSG:4326"
                )

                projected_crs = (
                    ksi_gdf.estimate_utm_crs()
                )

                if projected_crs is None:
                    projected_crs = (
                        "EPSG:3857"
                    )

                ksi_projected = (
                    ksi_gdf.to_crs(
                        projected_crs
                    )
                )

                edges_projected = (
                    edges.to_crs(
                        projected_crs
                    )
                )


            # -------------------------------------------------
            # SNAP CRASHES TO ROADS
            # -------------------------------------------------

            with st.spinner(
                "Snapping crashes to nearest roads..."
            ):

                joined = gpd.sjoin_nearest(
                    ksi_projected,
                    edges_projected,
                    how="left"
                )

                joined = joined.dropna(
                    subset=["segment_id"]
                )

                joined[
                    "segment_id"
                ] = joined[
                    "segment_id"
                ].astype(str)


            del ksi_projected
            del edges_projected


            # -------------------------------------------------
            # SCORE SEGMENTS
            # -------------------------------------------------

            with st.spinner(
                "Calculating High Injury Network..."
            ):

                scores = (
                    joined.groupby(
                        "segment_id"
                    )
                    .agg(
                        total_ksi=(
                            "segment_id",
                            "count"
                        ),
                        total_deaths=(
                            death_col,
                            "sum"
                        ),
                        total_serious=(
                            injury_col,
                            "sum"
                        )
                    )
                    .reset_index()
                )

                hin = scores[
                    scores["total_ksi"]
                    >= hin_threshold
                ]

                hin_edges = edges[
                    edges["segment_id"].isin(
                        hin["segment_id"]
                    )
                ]

                if not hin_edges.empty:

                    hin_edges = (
                        hin_edges.merge(
                            hin,
                            on="segment_id",
                            how="inner"
                        )
                    )

                    hin_edges = (
                        hin_edges.to_crs(
                            "EPSG:4326"
                        )
                    )


                st.session_state.hin_edges = (
                    hin_edges
                )

                st.session_state.ksi = (
                    ksi
                )

                st.session_state.lat_col = (
                    lat_col
                )

                st.session_state.lon_col = (
                    lon_col
                )

                st.session_state.death_col = (
                    death_col
                )

                st.session_state.hin_csv = (
                    hin.to_csv(
                        index=False
                    )
                )

                st.session_state.hin_count = (
                    len(hin)
                )

                st.session_state.hin_done = (
                    True
                )


                st.success(
                    f"Done! {len(hin):,} HIN segments found."
                )


# ---------------------------------------------------------
# RESULTS
# ---------------------------------------------------------

if st.session_state.hin_done:

    hin_edges = (
        st.session_state.hin_edges
    )

    ksi = (
        st.session_state.ksi
    )

    lat_col = (
        st.session_state.lat_col
    )

    lon_col = (
        st.session_state.lon_col
    )

    death_col = (
        st.session_state.death_col
    )

    show_hin = (
        st.session_state.show_hin
    )

    show_crashes = (
        st.session_state.show_crashes
    )

    basemap = (
        st.session_state.basemap
    )


    # -----------------------------------------------------
    # METRICS
    # -----------------------------------------------------

    col1, col2, col3, col4 = (
        st.columns(4)
    )

    col1.metric(
        "Total KSI Crashes",
        f"{len(ksi):,}"
    )

    col2.metric(
        "HIN Segments",
        f"{st.session_state.hin_count:,}"
    )

    fatal_count = int(
        (
            ksi[death_col]
            > 0
        ).sum()
    )

    col3.metric(
        "Fatal Crashes",
        f"{fatal_count:,}"
    )


    if (
        hin_edges is not None
        and
        not hin_edges.empty
    ):

        top_segment_ksi = int(
            hin_edges[
                "total_ksi"
            ].max()
        )

    else:

        top_segment_ksi = 0


    col4.metric(
        "Top Segment KSI",
        f"{top_segment_ksi:,}"
    )


    # -----------------------------------------------------
    # MAP
    # -----------------------------------------------------

    center_lat = float(
        ksi[lat_col].mean()
    )

    center_lon = float(
        ksi[lon_col].mean()
    )


    m = folium.Map(
        location=[
            center_lat,
            center_lon
        ],
        zoom_start=13,
        tiles=basemap
    )


    MiniMap(
        toggle_display=True
    ).add_to(m)


    MeasureControl(
        position="topleft"
    ).add_to(m)


    Draw(
        draw_options={
            "polyline": True,
            "polygon": True,
            "circle": False,
            "marker": True,
            "circlemarker": False,
            "rectangle": True
        },
        edit_options={
            "edit": True
        }
    ).add_to(m)


    # -----------------------------------------------------
    # HIN LAYER
    # -----------------------------------------------------

    if (
        show_hin
        and
        hin_edges is not None
        and
        not hin_edges.empty
    ):

        hin_layer = folium.FeatureGroup(
            name="High Injury Network",
            show=True
        )

        max_ksi = float(
            hin_edges[
                "total_ksi"
            ].max()
        )


        def hin_color(value):

            if max_ksi <= 0:
                return "#FF8C00"

            ratio = (
                float(value)
                / max_ksi
            )

            if ratio > 0.75:
                return "#8B0000"

            elif ratio > 0.50:
                return "#FF0000"

            elif ratio > 0.25:
                return "#FF4500"

            else:
                return "#FF8C00"


        for _, row in (
            hin_edges.iterrows()
        ):

            if (
                row.geometry
                is not None
                and
                not row.geometry.is_empty
            ):

                folium.GeoJson(
                    row.geometry.__geo_interface__,
                    style_function=(
                        lambda feature,
                        value=row[
                            "total_ksi"
                        ]:
                        {
                            "color": hin_color(
                                value
                            ),
                            "weight": 4,
                            "opacity": 0.9
                        }
                    ),
                    tooltip=folium.Tooltip(
                        f"<b>HIN Segment</b><br>"
                        f"KSI Crashes: "
                        f"{int(row['total_ksi'])}<br>"
                        f"Deaths: "
                        f"{int(row['total_deaths'])}<br>"
                        f"Serious Injuries: "
                        f"{int(row['total_serious'])}"
                    )
                ).add_to(
                    hin_layer
                )

        hin_layer.add_to(m)


    # -----------------------------------------------------
    # CRASH POINTS
    # -----------------------------------------------------

    if show_crashes:

        crash_layer = folium.FeatureGroup(
            name="KSI Crashes",
            show=True
        )

        # Keep this low to reduce map memory usage
        for _, row in (
            ksi.head(500).iterrows()
        ):

            if (
                pd.notna(
                    row[lat_col]
                )
                and
                pd.notna(
                    row[lon_col]
                )
            ):

                folium.CircleMarker(
                    location=[
                        float(
                            row[lat_col]
                        ),
                        float(
                            row[lon_col]
                        )
                    ],
                    radius=4,
                    color="yellow",
                    fill=True,
                    fill_opacity=0.7,
                    tooltip=(
                        f"Deaths: "
                        f"{int(row.get(death_col, 0))}"
                    )
                ).add_to(
                    crash_layer
                )

        crash_layer.add_to(m)


    # -----------------------------------------------------
    # LEGEND
    # -----------------------------------------------------

    legend_html = """
    <div style="
        position: fixed;
        bottom: 30px;
        right: 30px;
        z-index: 1000;
        background-color: rgba(0,0,0,0.8);
        padding: 15px;
        border-radius: 10px;
        color: white;
        font-family: Arial;
        font-size: 13px;
    ">
        <b>High Injury Network</b><br><br>
        <span style="color:#8B0000;">━━</span> Extreme<br>
        <span style="color:#FF0000;">━━</span> High<br>
        <span style="color:#FF4500;">━━</span> Medium<br>
        <span style="color:#FF8C00;">━━</span> Lower<br>
        <span style="color:yellow;">●</span> KSI Crash
    </div>
    """


    m.get_root().html.add_child(
        folium.Element(
            legend_html
        )
    )


    folium.LayerControl(
        position="topright",
        collapsed=False
    ).add_to(m)


    # -----------------------------------------------------
    # RENDER MAP WITHOUT STREAMLIT-FOLIUM
    # -----------------------------------------------------

    map_html = (
        m.get_root().render()
    )


    st.components.v1.html(
        map_html,
        height=650,
        scrolling=False
    )


    # -----------------------------------------------------
    # DOWNLOADS
    # -----------------------------------------------------

    st.subheader(
        "Download Results"
    )


    col1, col2 = (
        st.columns(2)
    )


    with col1:

        st.download_button(
            label="Download HIN CSV",
            data=st.session_state.hin_csv,
            file_name="hin_results.csv",
            mime="text/csv"
        )


    with col2:

        st.download_button(
            label="Download HIN Map",
            data=map_html,
            file_name="hin_map.html",
            mime="text/html"
        )


else:

    st.info(
        "Upload your crash data in the sidebar "
        "and click Generate HIN to get started."
    )
