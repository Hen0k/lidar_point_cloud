import json
import pdal
import geopandas as gpd
import laspy
import matplotlib.pyplot as plt
from shapely.geometry import Polygon, Point
from agritech_lidar.base import LiDARData
from pprint import pprint


class DataGetter(LiDARData):
    """
    A data getter class that inherites the LiDARData class
    I uses PDAL to fetch point cloud data for a specified locations.
    You can pass the filtering parameters in the initializer and
    get back the data in the format you want.

    Parameters
    ----------
    area_name: str
        The name for the area to look for. Will be looked in the available
        directories.
    boundaries: Polygon
        The geometric Polygon the requested area is in
    point_types: list[str]
        A list of strings of the requested point classes.
        It is enternally mapped to an integer representing the class name.
    intensity_threshold: float
        Used to only return points above the set threshold
    output_crs: str
        The projection format needed
    ouput_path: str
        Location for saving the file
    raw_pipeline_json: list[dict]
        A JSON object with the a raw PDAL format pipeline for fetching, processing,
        and saving point clouds using the ept format.

    Returns
    -------
    None
    """

    def __init__(self,
                 area_name: str = None,
                 boundaries: list[tuple] = None,
                 point_types: list[str] = None,
                 intensity_threshold: float = None,
                 output_crs: str = None,
                 ouput_path: str = "",
                 raw_pipeline_json: list[dict] = None
                 ) -> None:

        super().__init__()
        self.area_name = area_name
        self.boundaries = boundaries
        self.point_types = point_types
        self.intensity_threshold = intensity_threshold
        self.output_crs = output_crs
        self.ouput_path = ouput_path
        self.raw_pipeline_json = raw_pipeline_json

    def area_exists(self):
        if self.area_name and self.area_name in self.area_names:
            return True
        print(f"{self.area_name} not found")
        # pprint(self.area_names)
        return False

    def check_inclusion(self):
        area_variants = self.get_area_variants()
        # print("Variants")
        # print(area_variants)
        for _, variant in area_variants.iterrows():
            big_area = gpd.GeoDataFrame([Polygon([
                (variant['xmin'], variant['ymin']),
                (variant['xmin'], variant['ymax']),
                (variant['xmax'], variant['ymax']),
                (variant['xmax'], variant['ymin']),
            ])], columns=['geometry'])
            # print("BIG")
            # print(big_area.geometry[0])
            # print("SMALL")
            # print(self.small_rect.geometry[0])
            containes = big_area.geometry[0].contains(
                self.small_rect.geometry[0])
            if containes:
                # big_area.plot()
                # self.small_rect.plot()
                # plt.show()
                return variant['folder_name']
        # big_area.plot()
        # self.small_rect.plot()
        # plt.show()
        return False

    def boundary_within_area(self):
        if self.area_exists():
            # print("Area Does exist")
            return self.check_inclusion()
        return False

    def get_area_variants(self):
        variants = self.areas_metadata.query(f"area_name=='{self.area_name}'")
        return variants

    def build_pipeline(self):
        print("Building the Pipeline...")
        boundary_filter = self.create_boundary_filter()
        folder_name = self.boundary_within_area()
        print(f"folder_name: {folder_name}")
        if folder_name:
            json_pipeline_template = [
                {
                    "threads": 8, 
                    "type": "readers.ept",
                    "filename": f"{self.data_location}{folder_name}ept.json",
                }
            ]
            
            if boundary_filter:
                json_pipeline_template[0] = {
                    **json_pipeline_template[0],
                    **boundary_filter
                }
            points_filter_stage = self.create_point_filter()
            if points_filter_stage:
                json_pipeline_template.append(points_filter_stage)
            writer_stage = self.create_writer_stage()
            if writer_stage:
                json_pipeline_template.append(writer_stage)
            # print(json_pipeline_template)
            self.pipeline = pdal.Pipeline(json.dumps(json_pipeline_template))
            return self.pipeline

    def execute(self):
        if self.pipeline:
            output = self.pipeline.execute()
            return output
    
    def get_geodf(self):
        # Load the outputed data
        las = laspy.read(self.ouput_path)
        # collect points
        geometry = [Point((x, y)) for x, y in zip(las.x.array, las.y.array)]

        self.geo_df = gpd.GeoDataFrame(columns=["elevation", "geometry"])
        self.geo_df['geometry'] = geometry
        self.geo_df['elevation'] = las.z.array
        return self.geo_df
        


    def create_intensity_filter(self):
        pass

    def create_writer_stage(self):
        if self.ouput_path.endswith(".las"):
            return {
                "type": "writers.las",
                "filename": self.ouput_path
            }
        elif self.ouput_path.endswith(".tif"):
            return {
                "filename": self.ouput_path,
                "gdaldriver": "GTiff",
                "output_type": "all",
                "resolution": "5.0",
                "type": "writers.gdal"
            }

    def create_point_filter(self):
        if self.point_types:
            selections = []
            for point_name in self.point_types:
                point_idx = self.map_point_class(point_name)
                selections.append(f"Classification[{point_idx}:{point_idx}]")
            
            stage = {
                "type": "filters.range",
                "limits": str(selections)[1:-1].replace("'", '')
            }
            return stage

    def create_boundary_filter(self):
        if self.boundaries:
            xmin, ymin, xmax, ymax = self.get_rect_edges()
            return {"bounds": f"({[xmin, xmax]}, {[ymin, ymax]})"}
        return {}

    def get_rect_edges(self):
        """
        Converts a boundaries Polygon shape to geopandas bounds format.
        minx, miny, maxx, maxy

        """

        self.small_rect = gpd.GeoDataFrame([self.boundaries], columns=[
            'geometry'], crs="EPSG:3857")
        if self.small_rect.geometry[0].is_valid:
            xmin, ymin, xmax, ymax = self.small_rect.geometry[0].bounds
            return xmin, ymin, xmax, ymax
        else:
            raise "boundary geometry is invalid"

    def get_with_raw_pipeline(self, raw_pipeline_json):
        with open(raw_pipeline_json, 'r') as f:
            pipeline = pdal.Pipeline(f.read())
            counts = pipeline.execute()
            # print(counts)
            # print(pipeline.arrays)


if __name__ == "__main__":
    getter = DataGetter(area_name='USGS_LPC_TX_South_B8_2018_LAS',
                        boundaries=Polygon([
                            # (xmin, ymin)
                            (-10880908.0, 3040000),
                            # (xmin, ymax)
                            (-10880908.0, 3045000),
                            # (xmax, ymax)
                            (-10880830.0, 3045000),
                            # (xmax, ymin)
                            (-10880830.0, 3040000),
                        ]),
                        point_types=['Ground', 'Water'],
                        ouput_path="output/USGS_LPC_TX_South_B8_2018_LAS.las"
                        )
    pipeline = getter.build_pipeline()
    # print(pipeline)
    output = getter.execute()
    print(f"output: {output}")
    print(getter.pipeline.arrays[0])
    

