from typing import List
import numpy as np
from numpy.typing import NDArray

from compas_viewer import Viewer
from compas_viewer.scene import Tag

from compas.data import Data
from compas_acoustics import Defaults
from compas_acoustics import Tools

__all__ = ['Scene']

class Scene(Data):
    
    def __init__(self, name:str, description:str="", simulation_platform:str='pyroomacoustics'):
        super().__init__()
        self.name = name
        self.description = description
        self._acoustic_objects = []
        self._sources = []
        self._receivers = []
        self._acoustic_materials = {}
        self._supported_simulation_platforms = ['pyroomacoustics', 'acousticDE']
        self.simulation_platform = simulation_platform
        self.sampling_rate = Defaults().SAMPLING_RATE
        self.frequency_bands = Defaults().DEFAULT_FREQUENCY_BANDS
        # self.irs = None
        
        
    @property
    def id(self):
        return self.guid
    
    
    @property
    def acoustic_objects(self):
        return self._acoustic_objects
    
    
    @property
    def sources(self):
        all_sources = []
        
        # add standalone sources
        all_sources.extend(self._sources)
        
        # add sources from acoustic objects
        for acoustic_object in self.acoustic_objects:
            all_sources.extend(acoustic_object.sources)
        
        return all_sources
    
    
    @property
    def receivers(self):
        return self._receivers
    
    
    @property
    def number_of_acoustic_objects(self):
        return len(self._acoustic_objects)
    
    
    @property
    def number_of_sources(self):
        return len(self._sources)
    
    
    @property
    def number_of_receivers(self):
        return len(self._receivers)
    
    
    @property
    def description(self):
        return self._description
    
    
    @description.setter
    def description(self, description:str):
        self._description = description
        return self._description
    
    
    @property
    def name(self):
        return self._name
    
    
    @name.setter
    def name(self, name:str):
        self._name = name
        return self._name
    
    
    @property
    def acoustic_materials(self):
        return self._acoustic_materials
      
    
    
    def set_acoustic_materials(self, acoustic_materials:dict, resize_bands:str = "intersection"):
        """
        Make sure all materials in the scene have the same frequency bands.

        Parameters
        ----------
        acoustic_materials : dict
            dictionnary of compas.acoustic_material s
        resize_bands : str
            'intersection': truncates all frequency bands to the shortest common center frequencies of all scene materials.
            'union': fill missing frequency bands to match the longest common center frequencies of all scene materials by duplicating bound values.
        """
        all_bands = [m.frequency_bands for m in set(acoustic_materials.values())]

        if resize_bands == 'union':
            target_bands = sorted(set().union(*all_bands))
        else:  # intersection
            target_bands = sorted(set(all_bands[0]).intersection(*all_bands[1:]))

        for acoustic_material in set(acoustic_materials.values()):
            if acoustic_material.frequency_bands != target_bands:
                acoustic_material.resample_frequency_bands(target_bands)

        self.frequency_bands = target_bands
        self._acoustic_materials = acoustic_materials          
    
    
    @property
    def simulation_platform(self):
        return self._simulation_platform
    
    
    @property
    def supported_simulation_platforms(self):
        return self._supported_simulation_platforms
    
    
    @property
    def scene_surface_groups(self):
        surface_groups = []
        for acoustic_geometry in self.acoustic_objects:
            groups = acoustic_geometry.surface_groups.keys()
            surface_groups.extend(groups)
        return surface_groups
    
    
    def print_scene_surface_groups(self):
        print(f"Scene '{self.name}' surface groups:")
        for acoustic_geometry in self.acoustic_objects:
            print(f"Acoustic Object '{acoustic_geometry.name}':")
            for group_name in acoustic_geometry.surface_groups.keys():
                print(f"  {group_name}")
                
    
    def display_surface_groups(self):
        viewer = Viewer()
        
        for acoustic_geometry in self.acoustic_objects:
            group_colors = acoustic_geometry.surface_group_colors
            
            for fkey in acoustic_geometry.acoustic_geometry.faces():
                f_centroid = acoustic_geometry.acoustic_geometry.face_centroid(fkey)
                surface_group = acoustic_geometry.acoustic_geometry.face_attribute(fkey, 'surface_group')
                tag = Tag(surface_group, f_centroid, height=30, color=group_colors[surface_group])
                viewer.scene.add(tag, name=f"tag_{fkey}")
            
            viewer.scene.add(acoustic_geometry.acoustic_geometry, name=acoustic_geometry.name, show_points=True, facecolor=acoustic_geometry.face_colors)
        viewer.show()
    
    
    @simulation_platform.setter
    def simulation_platform(self, simulation_platform:str):
        if simulation_platform not in self._supported_simulation_platforms:
            raise ValueError(f"Simulation platform '{simulation_platform}' is not supported. Supported platforms are: {self._supported_simulation_platforms}")
        
        self._simulation_platform = simulation_platform
        
    
    def simulation(self, image_source_order=None, ray_tracing=None, n_rays=None, air_absorption=None, sampling_rate=None): # TODO Not all simulation methods need ray_tracing and image_source. Suggest remove from here
        simulation = None
        
        match self.simulation_platform:
            case 'pyroomacoustics':
                # prepare the walls and materials for the simulation
                kwargs = {k: v for k, v in {
                    'image_source_order': image_source_order,
                    'ray_tracing': ray_tracing,
                    'n_rays': n_rays,
                    'air_absorption': air_absorption,
                    'sampling_rate': sampling_rate,
                }.items() if v is not None}
                simulation = self._pyroomacoustics_simulation(**kwargs)
                
                # add sources and receivers to the simulation
                # TODO Create a unified definition for all simulation methods to check if source and receivers are inside Room 
                for source in self.sources:
                    if(simulation.is_inside(source.position)):
                        simulation.add_source(source.position)
                    else:
                        print(f"Warning: Source '{source.name}' is outside the room and will not be added to the simulation.")
                for receiver in self.receivers:
                    if(simulation.is_inside(receiver.position)):
                        simulation.add_microphone(receiver.position)
                    else:
                        print(f"Warning: Receiver '{receiver.name}' is outside the room and will not be added to the simulation.")
            case 'acousticDE':
                # prepare the walls and materials for the simulation
                simulation = self._acoustic_de_simulation()
            case _:
                raise NotImplementedError(f"Simulation platform '{self.simulation_platform}' is not implemented yet.")
            
        return simulation
    
    
    def _pyroomacoustics_simulation(self, image_source_order:int=3, ray_tracing:bool=False, n_rays:int=10000, air_absorption:bool=True, sampling_rate:int = None):
        import pyroomacoustics as pra
        import numpy as np
        

        # Number of frequencies bands that pyroomacoustics will use depending on frequency bands. Base_freq is hardcoded to 125 Hz because of Air absoprtion
        min_sampling_rate = 125 * (2 ** len(self.frequency_bands))
        max_sampling_rate = 125 * (2 ** (len(self.frequency_bands) + 1)) - 1

        if sampling_rate:
            if min_sampling_rate <= sampling_rate <= max_sampling_rate:
                self.sampling_rate = sampling_rate
            else:
                self.sampling_rate = max_sampling_rate
                print(f"Provided sampling rate does not match the acoustic materials frequency bands. Sampling rate was set to the closest value authorized by pyroomacoustics: {self.sampling_rate} Hz.")
        else:
            self.sampling_rate = max_sampling_rate
            print(f"Sampling rate was set to the maximum value authorized by pyroomacoustics regarding the specificied acoustic materials: {self.sampling_rate} Hz.")

        pyroom_frequency_bands = list(pra.acoustics.OctaveBandsFactory(fs = self.sampling_rate).centers)
        print(f"Pyroom_acoustics forced frequency bands: {pyroom_frequency_bands} for sampling rate: {self.sampling_rate} Hz.")        

        # create the walls
        walls = []
        for acoustic_geometry in self.acoustic_objects:
            for fkey in acoustic_geometry.acoustic_geometry.faces():
                # verticies of the face
                face_vertices = acoustic_geometry.acoustic_geometry.face_vertices(fkey)
                pts = np.asarray([acoustic_geometry.acoustic_geometry.vertex_coordinates(vkey) for vkey in face_vertices])
                
                # acoustic material of the face
                surface_group = acoustic_geometry.acoustic_geometry.face_attribute(fkey, 'surface_group')
                acoustic_material = acoustic_geometry.acoustic_materials.get(surface_group, None)
                if acoustic_material is None:
                    acoustic_material = self.acoustic_materials.get(surface_group, None)
                    if acoustic_material is None:
                        raise ValueError(f"No acoustic material assigned to surface group '{surface_group}'.")

                if set(acoustic_material.frequency_bands) != set(pyroom_frequency_bands):
                    acoustic_material.resample_frequency_bands(pyroom_frequency_bands)  
                material_settings = {
                    'description': acoustic_material.name,
                    'coeffs': acoustic_material.absorption_coefficients,
                    'scattering': acoustic_material.scattering_coefficients,
                    'center_freqs': acoustic_material.frequency_bands
                }
                
                mat = pra.Material(material_settings)
                    
                # mat = pra.Material(energy_absorption=acoustic_material.absorption_coefficients, scattering=acoustic_material.scattering_coefficients)
               
                # create wall
                wall = pra.wall_factory(pts.T,
                                        mat.energy_absorption['coeffs'],
                                        mat.scattering['coeffs'])
                walls.append(wall)
                            
        # create the room
        room = pra.Room(
            walls,
            fs=self.sampling_rate,
            max_order=image_source_order,
            ray_tracing=ray_tracing,
            air_absorption=air_absorption,
        )
        
        print(f"Simulation setting:\n"+
              f"Sampling rate={self.sampling_rate}\n"+
              f"Image source order={image_source_order}\n"+
              f"Air absorption={air_absorption}"
              )
        
        if ray_tracing:
            room.set_ray_tracing(n_rays=n_rays)
            print(f"Ray tracing={ray_tracing}\n"+
                f"N rays={n_rays}\n")

        return room
    

    def rir_from_image_source_method(self, image_source_order:int=3, air_absorption:bool=True): 
        simulation = self.simulation(image_source_order=image_source_order, ray_tracing=False, n_rays=10000, air_absorption=air_absorption)
        simulation.image_source_model()
        simulation.compute_rir()
        
        return self.resample_room_rir(room_rir=simulation.rir, orig_sr=simulation.fs, target_sr=self.sampling_rate)
    
    
    def rir_from_ray_tracing(self, image_source_order:int=3, n_rays:int=10000, air_absorption:bool=True):
        simulation = self.simulation(image_source_order=image_source_order, ray_tracing=True, n_rays=n_rays, air_absorption=air_absorption)
        simulation.compute_rir()
        
        return self.resample_room_rir(room_rir=simulation.rir, orig_sr=simulation.fs, target_sr=self.sampling_rate)
    
    
    def resample_room_rir(self, room_rir:List[List], orig_sr:int, target_sr:int, method:str = "poly") -> List[List[NDArray[np.float64]]]:
        """
        Resample all impulse responses in a pyroomacoustics room.rir structure.

        Parameters
        ----------
        room_rir : Sequence[Sequence[ArrayLike]]
            room.rir structure:
            room_rir[mic_idx][source_idx] -> 1D impulse response
        orig_sr : int
            Original sample rate.
        target_sr : int
            Target sample rate.
        method : str, default="poly"
            Resampling method passed to resample_ir().

        Returns
        -------
        List[List[NDArray[np.float64]]]
            Resampled room.rir with the same nested-list structure.
        """

        return [
            [Tools().resample_signal(ir, orig_sr, target_sr, method=method) for ir in mic_rirs]
            for mic_rirs in room_rir
        ]
    
    def _acoustic_de_simulation(self, mesh_resolution:float=1.0, fc_low:int=125, fc_high:int=8000, num_octave:int=1, dt:float= 1/20000, air_absorption:bool=True, th:int=3, tcalc:str="decay"):
        """
        Simulate the energy decay in the Scene using the Finite Volume diffusion equation, using acousticDE package.

        Parameters
        ----------
        mesh_resolution: float
            subdivision of the Finite Element Mesh in meters.
        fc_low: int
            lowest frequency band.
        fc_high: int
            highest frequency band.
        num_octave: int
            1 or 3 depending on how many octave per band you want.
        dt: float
            time discretization
        air_absorption:  bool
            air absorption coefficient // only one value for all the frequency bands
        th: int
            Enter type Absorption conditions (option 1,2,3):")) # options Sabine (th=1), Eyring (th=2) and modified by Xiang (th=3)
        tcalc: str
            Choose "decay" if the objective is to calculate the energy decay of the room with all its energetic parameters; Choose "stationarysource" if the aim is to understand the behaviour of a room subject to a stationary source

        Returns
        -------
        result: dict[str, Unknown]
            Results are saved at the root as resultsFVM.pkl
            and are returned as a dictionnary, containing: coord_source, coord_rec, fc_low, fc_high, num_octave, dt, m_atm, th, tcalc, df_abs, center_freq, t, w_new_band, w_rec_band, w_rec_off_band, w_rec_off_deriv_band, p_rec_off_deriv_band, idx_w_rec, t_off, w_rec_x_band, w_rec_y_band, spl_stat_x_band, spl_stat_y_band, spl_r_band, spl_r_off_band, spl_r_norm_band, sch_db_band, spl_r_t0_band, t30_band, t20_band, edt_band, c80_band, d50_band, ts_band

        References
        -------
        J. M. Navarro, J. Escolano and J. J. Lopez, Implementation and evaluation of a diffusion equation model based on finite difference schemes for sound field prediction in rooms, Applied Acoustics 73 (2012).
        R. P. Muñoz, Numerical modeling for urban sound propagation: developments in wave-based and energy based methods, PhD Thesis, Technische Universiteit Eindhoven, 2019.

        """


        import os
        import tempfile
        import pandas as pd
        import json
        from acousticDE.FiniteVolumeMethod.FVMfunctions import number_freq
        from acousticDE.FiniteVolumeMethod.FVM import run_fvm_sim

        temp_dir = tempfile.TemporaryDirectory()
        script_dir = temp_dir.name
        geo_path = os.path.join(script_dir, f"{self.name}.geo")
        gmsh_path = os.path.join(script_dir, f"{self.name}.msh")

        input_data = {
            "fc_low": fc_low, #lowest frequency
            "fc_high": fc_high, #highest frequency
            "num_octave": num_octave, # 1 or 3 depending on how many octave you want
            "dt": dt, #time discretization
            "m_atm": 0.0025 if air_absorption else 0, #air absorption coefficient // energy-based and not frequency dependant
            "th": th, #int(input("Enter type Absorption conditions (option 1,2,3):")) # options Sabine (th=1), Eyring (th=2) and modified by Xiang (th=3)
            "tcalc": tcalc #Choose "decay" if the objective is to calculate the energy decay of the room with all its energetic parameters; Choose "stationarysource" if the aim is to understand the behaviour of a room subject to a stationary source
        } 

        surface_names = []
        absorption_coefficients_list = []
        
        # Get the number of frequency bands and their center frequencies for the
        # specified frequency range and number of octaves
        _nBands, center_freq = number_freq(
            input_data["num_octave"],
            input_data["fc_high"], input_data["fc_low"])
        
        # Create DataFrame containing the absorption coefficients
        column_names = ["Material"] + [f"{int(fc)}Hz" for fc in center_freq]
        csv_path = os.path.join(script_dir, "absorption_coefficients.csv")   

        # Run gmsh FVM mesher     
        self._compas_to_gmsh(geo_path, gmsh_path, mesh_resolution)

        for acoustic_geometry in self.acoustic_objects:
            for fkey in acoustic_geometry.acoustic_geometry.faces():
                
                # acoustic material of the face
                surface_group = acoustic_geometry.acoustic_geometry.face_attribute(fkey, 'surface_group')
                acoustic_material = acoustic_geometry.acoustic_materials.get(surface_group, None)
                if acoustic_material is None:
                    acoustic_material = self.acoustic_materials.get(surface_group, None)
                    if acoustic_material is None:
                        raise ValueError(f"No acoustic material assigned to surface group '{surface_group}'.")

                surface_names.append(surface_group)
                absorption_coefficients_list.append(acoustic_material.absorption_coefficients)

        absorption_coefficients = pd.DataFrame(columns=column_names)
        absorption_coefficients["Material"] = surface_names
        absorption_coefficients[absorption_coefficients.columns[1:]] = absorption_coefficients_list
        absorption_coefficients.to_csv(csv_path, index=False)
        print(f"created csv material file \n {absorption_coefficients}")            

        
        for sid , source in enumerate(self.sources):
            for rid, receiver in enumerate(self.receivers):
                extra_data = {
                    "coord_source": source.position, #source coordinates x,y,z
                    "coord_rec": receiver.position, #rec coordinates x,y,z
                    }
                input_data = extra_data | input_data 

                fname_input_configuration = f"{self.name}_S{sid}_R{rid}.json"
                with open(os.path.join(script_dir, fname_input_configuration), "w") as f:
                    json.dump(input_data, f, indent=4)

                print(f"Input file successfully created: {fname_input_configuration}")        

                # Run the simulation
                result = run_fvm_sim(
                    gmsh_path,
                    os.path.join(script_dir, fname_input_configuration),
                    csv_path)

                print("Reverberation time T30 band values:", result["t30_band"])
                print("Early decay time EDT band values:", result["edt_band"])
                print("Clarity C80 band values:", result["c80_band"])
                print("Definition D50 band values:", result["d50_band"])
                print("Centre time Ts band values:", result["ts_band"])

        return result

    
    def _compas_to_gmsh(self, geo_path, name_gmsh_file, characteristic_length):
        """
        Converts Compas mesh into .geo file then .msh file,
        create Lines with consistent orientation and Line Loops with signed line indices,
        and genrerates gmsh mesh with Physical Surface groups and a physical volume.

        Adapted from code by  @author: Ilaria Fichera
        """

        import gmsh
        
        with open(geo_path, "w") as g:
            total_vertices = 0
            lid = 0
            loop_id = 0
            surface_loop_id = 0
            face_to_surface_id = {}
            idf = 0
            vertex_offset = 0
            for acoustic_geometry in self.acoustic_objects:    
                # --- Points (1-based IDs with global offset) ---
                n_vertices = acoustic_geometry.acoustic_geometry.number_of_vertices()
                for v in acoustic_geometry.acoustic_geometry.vertices():
                    pt = acoustic_geometry.acoustic_geometry.vertex_point(v)
                    g.write(f"Point({vertex_offset + int(v) + 1}) = {{ {pt.x}, {pt.y}, {pt.z}, 1.0 }};\n")
                total_vertices += n_vertices
                g.write("\n")

                # --- Lines with offset point references ---
                edge_to_signed_lid = {}  # reset per object; keys are local vertex indices
                for edge in acoustic_geometry.acoustic_geometry.edges():
                    u, v = edge
                    lid += 1
                    g.write(f"Line({lid}) = {{ {vertex_offset + int(u) + 1}, {vertex_offset + int(v) + 1} }};\n")
                    edge_to_signed_lid[(u, v)] = lid
                    edge_to_signed_lid[(v, u)] = -lid
                g.write("\n")

                # --- Line Loops (one per face, ordered) ---
                face_to_loop_id = {}
                for face in acoustic_geometry.acoustic_geometry.faces():
                    loop_id += 1
                    face_to_loop_id[face] = loop_id
                    face_vertices = acoustic_geometry.acoustic_geometry.face_vertices(face)
                    face_lines = []
                    for i in range(len(face_vertices)):
                        u = face_vertices[i]
                        v = face_vertices[(i + 1) % len(face_vertices)]
                        face_lines.append(edge_to_signed_lid[(u, v)])
                    lines_str = ", ".join(map(str, face_lines))
                    g.write(f"Line Loop({loop_id}) = {{ {lines_str} }};\n")
                g.write("\n")

                # --- Plane Surfaces and Surface Loops ---
                connected_faces = acoustic_geometry.acoustic_geometry.connected_faces()
                
                for idx, group in enumerate(connected_faces):
                    surface_loop_id += 1
                    group_surface_ids = []
                    for face in group:
                        idf += 1
                        face_to_surface_id[face] = idf
                        group_surface_ids.append(idf)
                        g.write(f"Plane Surface({idf}) = {{ {face_to_loop_id[face]} }};\n")
                    surface_ids_str = ", ".join(map(str, group_surface_ids))
                    g.write(f"Surface Loop({surface_loop_id}) = {{ {surface_ids_str} }};\n")
                g.write("\n")

                # --- Physical Surfaces (using surface IDs, not face keys) ---
                for name, indices in acoustic_geometry.surface_groups.items():
                    surface_ids = [face_to_surface_id[face] for face in indices if face in face_to_surface_id]
                    if surface_ids:
                        indices_str = ", ".join(map(str, surface_ids))
                        g.write(f'Physical Surface("{name}") = {{ {indices_str} }};\n')
                g.write("\n")

                vertex_offset += n_vertices

            g.write("Volume(1) = { 1 };\n")
            g.write(f'Physical Volume("{"RoomVolume"}") = {{ 1 }};\n')

            # Physical Line (all lines)
            lines_all = ", ".join(str(i) for i in range(1, lid+1))
            g.write(f'Physical Line("default") = {{ {lines_all} }};\n')

            g.write('Mesh.Algorithm = 6;\n')
            g.write('Mesh.Algorithm3D = 1; // Delaunay3D, works for boundary layer insertion.\n')
            g.write('Mesh.Optimize = 1; // Gmsh smoother, works with boundary layers (netgen version does not).\n')
            g.write('Mesh.CharacteristicLengthFromPoints = 1;\n')
            g.write('// Recombine Surface "*";\n')

        print(f"Wrote {geo_path}: {total_vertices} points, {lid} lines, {idf} surfaces.")
        
        # Read the content of the Geo file
        with open(geo_path, 'r') as file:
            geo_content = file.readlines()

        # Specify the line to be removed
        line_to_remove = 'Mesh.RemeshAlgorithm = 1; // automatic\n'

        # Remove the specified line from the content
        if line_to_remove in geo_content:
            geo_content.remove(line_to_remove)
            
        # Write the modified content back to the Geo file
        with open(geo_path, 'w') as file:
            file.writelines(geo_content)

        # If an lc is given in the geo file, we want to compensate for this
        lc_value = 1 # set to 1 by default
        for line in geo_content:
            if "lc =" in line:
                lc_value = float(line.split('=')[1].strip().strip(';'))
                print("Extracted value:", lc_value)
                break

        should_initialise_gmsh = False
        if not gmsh.is_initialized():
            should_initialise_gmsh = True

        if should_initialise_gmsh:
            gmsh.initialize()
        gmsh.open(geo_path)

        # Divide by the lc value given in the .geo file to get a correct characteristic length 
        gmsh.option.setNumber('Mesh.MeshSizeFactor', characteristic_length / lc_value)
        print(f"Mesh size factor: {characteristic_length / lc_value}")

        gmsh.model.mesh.generate(3)
        print(gmsh.logger.get())
        gmsh.write(name_gmsh_file)

        # mesh = gmsh.open(name_gmsh_file)  # open the file
        # gmsh.fltk.run()  # run the file to see it in gmsh

        if should_initialise_gmsh:
            gmsh.finalize()        



    def add_acoustic_object(self, acoustic_object):
        self._acoustic_objects.append(acoustic_object)
        
    
    def add_acoustic_objects(self, acoustic_objects:list):
        self._acoustic_objects.extend(acoustic_objects)


    def add_source(self, source):
        self._sources.append(source)

    def add_receiver(self, receiver):
        self._receivers.append(receiver)
