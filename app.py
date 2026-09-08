import streamlit as st
import pandas as pd
import geopandas as gpd
import folium
from folium.plugins import Draw, MeasureControl, MiniMap
import osmnx as ox
from streamlit_folium import st_folium
import os

st.set_page_config(layout="wide", page_title="High Injury Network Analyzer")

@st.cache_data(ttl=86400)
def get_road_network(city):
    try:
        ox.settings.requests_timeout = 180
        G = ox.graph_from_place(city, network_type='drive', simplify=True)
        edges = ox.graph_to_gdfs(G, nodes=False).reset_index()
        edges['osmid'] = edges['osmid'].apply(
            lambda x: x[0] if isinstance(x, list) else x
        ).astype(str)
        return edges
    except Exception as e:
        return None

st.title('High Injury Network Analyzer')

# Initialize session state
for key in ['hin_done', 'hin_map', 'hin_csv', 'hin_count', 'hin_edges', 'ksi', 'lat_col', 'lon_col', 'death_col', 'show_hin', 'show_crashes', 'basemap']:
    if key not in st.session_state:
        st.session_state[key] = None
if 'hin_done' not in st.session_state:
    st.session_state.hin_done = False

# Sidebar
with st.sidebar:
    st.header('Controls')
    uploaded_file = st.file_uploader('Upload crash CSV file', type=['csv'])

    if uploaded_file is not None:
        df = pd.read_csv(uploaded_file, low_memory=False)
        st.success(f'Loaded {len(df):,} crashes')

        st.subheader('Map Columns')
        st.caption('Required fields')
        lat_col = st.selectbox('Latitude column', df.columns)
        lon_col = st.selectbox('Longitude column', df.columns)
        death_col = st.selectbox('Death count column', df.columns)
        injury_col = st.selectbox('Serious injury column', df.columns)
        city = st.text_input('City name', 'Austin, Texas, USA')

        st.subheader('Optional Filters')
        st.caption('Leave as None to include all crash types')
        optional_cols = ['None'] + list(df.columns)
        ped_death_col = st.selectbox('Pedestrian death column', optional_cols)
        ped_injury_col = st.selectbox('Pedestrian injury column', optional_cols)
        bike_death_col = st.selectbox('Bike death column', optional_cols)
        bike_injury_col = st.selectbox('Bike injury column', optional_cols)

        st.subheader('HIN Mode')
        hin_mode = st.radio(
            'Generate HIN for:',
            ['All KSI crashes', 'Pedestrian crashes only', 'Bike crashes only', 'Pedestrian + Bike only']
        )

        st.subheader('HIN Settings')
        hin_threshold = st.slider('Minimum KSI crashes for HIN', 1, 10, 2)

        st.subheader('Map Display')
        show_crashes = st.checkbox('Show crash points', value=True)
        show_hin = st.checkbox('Show HIN segments', value=True)
        basemap = st.selectbox('Basemap', [
            'CartoDB dark_matter',
            'CartoDB positron',
            'OpenStreetMap'
        ])

        generate = st.button('Generate HIN', type='primary')

        if generate:
            st.session_state.hin_done = False
            st.session_state.show_hin = show_hin
            st.session_state.show_crashes = show_crashes
            st.session_state.basemap = basemap

            # Clean data
            with st.spinner('Cleaning data...'):
                df = df.dropna(subset=[lat_col, lon_col])
                df = df[(df[lat_col] != 0) & (df[lon_col] != 0)]
                df[death_col] = pd.to_numeric(df[death_col], errors='coerce').fillna(0)
                df[injury_col] = pd.to_numeric(df[injury_col], errors='coerce').fillna(0)
                all_ksi = df[(df[death_col] > 0) | (df[injury_col] > 0)].copy()

            # Apply HIN mode filter
            if hin_mode == 'All KSI crashes':
                ksi = all_ksi

            elif hin_mode == 'Pedestrian crashes only':
                if ped_death_col != 'None' or ped_injury_col != 'None':
                    ped_filter = pd.Series([False] * len(all_ksi), index=all_ksi.index)
                    if ped_death_col != 'None':
                        all_ksi[ped_death_col] = pd.to_numeric(all_ksi[ped_death_col], errors='coerce').fillna(0)
                        ped_filter = ped_filter | (all_ksi[ped_death_col] > 0)
                    if ped_injury_col != 'None':
                        all_ksi[ped_injury_col] = pd.to_numeric(all_ksi[ped_injury_col], errors='coerce').fillna(0)
                        ped_filter = ped_filter | (all_ksi[ped_injury_col] > 0)
                    ksi = all_ksi[ped_filter].copy()
                else:
                    st.warning('Please select at least one pedestrian column')
                    st.stop()

            elif hin_mode == 'Bike crashes only':
                if bike_death_col != 'None' or bike_injury_col != 'None':
                    bike_filter = pd.Series([False] * len(all_ksi), index=all_ksi.index)
                    if bike_death_col != 'None':
                        all_ksi[bike_death_col] = pd.to_numeric(all_ksi[bike_death_col], errors='coerce').fillna(0)
                        bike_filter = bike_filter | (all_ksi[bike_death_col] > 0)
                    if bike_injury_col != 'None':
                        all_ksi[bike_injury_col] = pd.to_numeric(all_ksi[bike_injury_col], errors='coerce').fillna(0)
                        bike_filter = bike_filter | (all_ksi[bike_injury_col] > 0)
                    ksi = all_ksi[bike_filter].copy()
                else:
                    st.warning('Please select at least one bike column')
                    st.stop()

            elif hin_mode == 'Pedestrian + Bike only':
                combined_filter = pd.Series([False] * len(all_ksi), index=all_ksi.index)
                for col in [ped_death_col, ped_injury_col, bike_death_col, bike_injury_col]:
                    if col != 'None':
                        all_ksi[col] = pd.to_numeric(all_ksi[col], errors='coerce').fillna(0)
                        combined_filter = combined_filter | (all_ksi[col] > 0)
                if combined_filter.any():
                    ksi = all_ksi[combined_filter].copy()
                else:
                    st.warning('Please select at least one pedestrian or bike column')
                    st.stop()

            st.write(f'KSI crashes: {len(ksi):,}')

            # Road network — cached
            with st.spinner('Downloading road network (first time takes 2-3 mins, cached after)...'):
                edges = get_road_network(city)
                if edges is None:
                    st.error('Could not download road network. Check city name and try again.')
                    st.stop()

            # Snap crashes to roads
            with st.spinner('Snapping crashes to roads...'):
                ksi_gdf = gpd.GeoDataFrame(
                    ksi,
                    geometry=gpd.points_from_xy(ksi[lon_col], ksi[lat_col]),
                    crs='EPSG:4326'
                )
                joined = gpd.sjoin_nearest(
                    ksi_gdf.to_crs('EPSG:3857'),
                    edges.to_crs('EPSG:3857'),
                    how='left'
                )
                joined['osmid'] = joined['osmid'].apply(
                    lambda x: x[0] if isinstance(x, list) else x
                ).astype(str)

            # Score segments
            with st.spinner('Scoring segments...'):
                scores = joined.groupby('osmid').agg(
                    total_ksi=('osmid', 'count'),
                    total_deaths=(death_col, 'sum'),
                    total_serious=(injury_col, 'sum')
                ).reset_index()
                hin = scores[scores['total_ksi'] >= hin_threshold].copy()
                hin_edges = edges[edges['osmid'].isin(hin['osmid'])].copy()
                hin_edges = hin_edges.merge(hin, on='osmid').to_crs('EPSG:4326')

                st.session_state.hin_edges = hin_edges
                st.session_state.ksi = ksi
                st.session_state.lat_col = lat_col
                st.session_state.lon_col = lon_col
                st.session_state.death_col = death_col
                st.session_state.hin_csv = hin.to_csv(index=False)
                st.session_state.hin_count = len(hin)
                st.session_state.hin_done = True
                st.success(f'Done! {len(hin):,} HIN segments found')

# Main area
if st.session_state.hin_done:

    hin_edges = st.session_state.hin_edges
    ksi = st.session_state.ksi
    lat_col = st.session_state.lat_col
    lon_col = st.session_state.lon_col
    death_col = st.session_state.death_col
    show_hin = st.session_state.show_hin
    show_crashes = st.session_state.show_crashes
    basemap = st.session_state.basemap

    # Metrics
    col1, col2, col3, col4 = st.columns(4)
    col1.metric('Total KSI Crashes', f'{len(ksi):,}')
    col2.metric('HIN Segments', f'{st.session_state.hin_count:,}')
    fatal_count = int((ksi[death_col] > 0).sum())
    col3.metric('Fatal Crashes', f'{fatal_count:,}')
    col4.metric('Top Segment KSI', f'{int(hin_edges["total_ksi"].max()):,}')

    # Build map
    center_lat = ksi[lat_col].mean()
    center_lon = ksi[lon_col].mean()

    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=13,
        tiles=basemap
    )

    MiniMap(toggle_display=True).add_to(m)
    MeasureControl(position='topleft').add_to(m)
    Draw(
        draw_options={
            'polyline': True,
            'polygon': True,
            'circle': False,
            'marker': True,
            'circlemarker': False,
            'rectangle': True
        },
        edit_options={'edit': True}
    ).add_to(m)

    # HIN layer
    if show_hin:
        hin_layer = folium.FeatureGroup(name='High Injury Network', show=True)
        max_ksi = hin_edges['total_ksi'].max()

        def hin_color(val):
            ratio = val / max_ksi
            if ratio > 0.75:
                return '#8B0000'
            elif ratio > 0.5:
                return '#FF0000'
            elif ratio > 0.25:
                return '#FF4500'
            else:
                return '#FF8C00'

        for _, row in hin_edges.iterrows():
            if row.geometry is not None:
                folium.GeoJson(
                    row.geometry.__geo_interface__,
                    style_function=lambda x, v=row['total_ksi']: {
                        'color': hin_color(v),
                        'weight': 4,
                        'opacity': 0.9
                    },
                    tooltip=folium.Tooltip(
                        f"<b>HIN Segment</b><br>KSI: {row['total_ksi']}<br>"
                        f"Deaths: {int(row['total_deaths'])}<br>"
                        f"Serious Injuries: {int(row['total_serious'])}"
                    )
                ).add_to(hin_layer)
        hin_layer.add_to(m)

    # Crash points layer
    if show_crashes:
        crash_layer = folium.FeatureGroup(name='KSI Crashes', show=True)
        for _, row in ksi.head(3000).iterrows():
            if pd.notna(row[lat_col]) and pd.notna(row[lon_col]):
                folium.CircleMarker(
                    location=[row[lat_col], row[lon_col]],
                    radius=4,
                    color='yellow',
                    fill=True,
                    fill_opacity=0.7,
                    tooltip=f"Deaths: {int(row.get(death_col, 0))}"
                ).add_to(crash_layer)
        crash_layer.add_to(m)

    # Legend
    legend_html = '''
    <div style="position: fixed; bottom: 30px; right: 30px; z-index: 1000;
                background-color: rgba(0,0,0,0.8); padding: 15px;
                border-radius: 10px; color: white; font-family: Arial; font-size: 13px;">
        <b>High Injury Network</b><br><br>
        <i style="background:#8B0000; width:20px; height:4px; display:inline-block; margin-right:8px;"></i> Extreme<br>
        <i style="background:#FF0000; width:20px; height:4px; display:inline-block; margin-right:8px;"></i> High<br>
        <i style="background:#FF4500; width:20px; height:4px; display:inline-block; margin-right:8px;"></i> Medium<br>
        <i style="background:#FF8C00; width:20px; height:4px; display:inline-block; margin-right:8px;"></i> Lower<br>
        <i style="background:yellow; border-radius:50%; width:10px; height:10px;
                  display:inline-block; margin-right:8px;"></i> KSI Crash<br>
    </div>
    '''
    m.get_root().html.add_child(folium.Element(legend_html))
    folium.LayerControl(position='topright', collapsed=False).add_to(m)

    st_folium(m, width=None, height=600, returned_objects=[])

    m.save('hin_map.html')

    st.subheader('Download Results')
    col1, col2 = st.columns(2)
    with col1:
        st.download_button(
            label='Download HIN CSV',
            data=st.session_state.hin_csv,
            file_name='hin_results.csv',
            mime='text/csv'
        )
    with col2:
        with open('hin_map.html', 'r') as f:
            st.download_button(
                label='Download HIN Map',
                data=f,
                file_name='hin_map.html',
                mime='text/html'
            )

else:
    st.info('Upload your crash data in the sidebar and click Generate HIN to get started')