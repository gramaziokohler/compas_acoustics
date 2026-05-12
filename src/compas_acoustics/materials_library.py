from compas.data import Data
from compas.data import json_load

from compas_acoustics.defaults import Defaults
from compas_acoustics.acoustic_material import AcousticMaterial

import os


__all__ = ['MaterialsLibrary']


class MaterialsLibrary(Data):
    """
    A class for handling acoustic materials.
    """


    def __init__(self):
        self._library_path = Defaults().MATERIALS_LIBRARY_PATH
    
    
    def material_from_name(self, material_name: str) -> AcousticMaterial:
        """Retrieve an AcousticMaterial instance by its name.
        
        Parameters
        ----------
        material_name : str
            The identifier of the acoustic material.
        
        Returns
        -------
        AcousticMaterial
            An instance of AcousticMaterial.
        """
        path = self.path_from_material_name(material_name)
        return self.material_from_json(path)
    
    
    def material_from_json(self, path: str) -> AcousticMaterial:
        """Create an AcousticMaterial instance from JSON data.
        
        Parameters
        ----------
        path : str
            The path to the JSON file containing material properties.
        
        Returns
        -------
        AcousticMaterial
            An instance of AcousticMaterial.
        """
        material = json_load(path)
        return material


    def path_from_material_name(self, material_name: str) -> str:
        """Construct the path to a JSON file for an AcousticMaterial by its name.
        
        Parameters
        ----------
        material_name : str
            The identifier of the acoustic material.
        
        Returns
        -------
        str
            The path to the JSON file for the specified material.
        """
        
        return os.path.join(self._library_path, f"{material_name}.json")


    @property
    def material_names(self) -> list:
        """List of all material names in the library.
        
        Returns
        -------
        list
            A list of material names.
        """
        material_files = [f for f in os.listdir(self._library_path) if f.endswith('.json')]
        material_names = [os.path.splitext(f)[0] for f in material_files]
        return material_names
    
    
    # ─── Absorption coefficient builder ──────────────────────────────────────────
    ## Experiment to build dynamic number of bands for acoustic materials depending on simulation requirments
    ## (when using multiple materials that do not have the same number of frequency bands (it is the case for pyroomacoustics database),
    ## solve pyroomacoustics samplerate dependency, Diffusion Equation sub-octave bands, etc...)




    # def build_material_absorption_dict(
    #     object_ids: list[str],
    #     object_material_names: dict[str, str],
    #     frequencies: list[int],
    #     material_database: Optional[dict] = None,
    # ) -> dict[str, str]:
    #     """
    #     Build the ``absorption_coefficients`` dict for a Choras JSON input.

    #     Each entry maps a Speckle object ID (used as the Physical Surface name in
    #     the GEO file) to a comma-separated string of absorption coefficients at
    #     the requested frequency bands.

    #     Args:
    #         object_ids: List of Speckle object IDs present in the geometry.
    #         object_material_names: ``{object_id: material_id}`` from the frontend.
    #             Material IDs may carry a "choras2_" prefix which is stripped.
    #         frequencies: List of octave-band centre frequencies (e.g. [125, 250, 500, 1000, 2000]).
    #         material_database: Override for ``CHORAS_ABSORPTION_MATERIALS``.

    #     Returns:
    #         ``{object_id: "0.6, 0.69, 0.71, 0.70, 0.63", ...}``
    #     """
    #     if material_database is None:
    #         material_database = CHORAS_ABSORPTION_MATERIALS

    #     result: dict[str, str] = {}
    #     n = len(frequencies)
    #     fallback_key = "medium_absorber"

    #     for obj_id in object_ids:
    #         raw_mat = object_material_names.get(obj_id, fallback_key)
    #         # Strip any frontend prefix (e.g. "choras2_carpet_thick" → "carpet_thick")
    #         mat_name = raw_mat
    #         for prefix in ("choras2_", "choras_", "pyroom_"):
    #             if mat_name.startswith(prefix):
    #                 mat_name = mat_name[len(prefix):]
    #                 break

    #         material = material_database.get(mat_name, material_database.get(fallback_key, {}))
    #         coeffs: list[float] = list(material.get("coeffs", [0.5] * n))

    #         # Pad or trim to match requested number of frequencies
    #         if len(coeffs) < n:
    #             coeffs = coeffs + [coeffs[-1]] * (n - len(coeffs))
    #         else:
    #             coeffs = coeffs[:n]

    #         result[obj_id] = ", ".join(str(c) for c in coeffs)

    #     return result    