A simple simulation in a shoebox room

A 5 × 4 × 3 m room with a different material on its floor, walls and ceiling, a source and a receiver facing
each other, simulated with image sources and ray tracing. The definition reads the reverberation time T30 of the
pair and plots it per octave band, and auralises it. It builds the same room as the Python version, wall
for wall.

1. **Room.** A room drawn in Rhino would come in through a Mesh or Brep parameter; here Box 2Pt makes one from
   (0, 0, 0) to (5, 4, 3). Deconstruct Brep splits it into its six faces, List Item puts them in the
   order floor, right, front, left and back wall, ceiling, and Mesh Brep turns each into a mesh, the geometry an
   acoustic object takes.
2. **Materials.** Four [Construct Material](../components/CA_Construct_Material.md) components each take seven absorption
   coefficients (125 Hz to 8 kHz) and seven scattering coefficients, or one for every band. Merge lists one material
   per wall, in the order of the walls. A material from the library would come from
   [Material Library](../components/CA_Material_Library.md) instead.
3. **Acoustic objects.** [Acoustic Object](../components/CA_Acoustic_Object.md) pairs each wall with its material and name.
   Its role is *boundary*: the walls enclose the room.
4. **Source and receiver.** A [Source](../components/CA_Source.md) at (4, 3, 1.5) and a [Receiver](../components/CA_Receiver.md)
   at (1, 1, 1.1), each with a name and a direction that points at the other.
5. **Scene and simulation.** [Acoustic Scene](../components/CA_Model.md) collects the walls, sources and receivers and reports
   the room's volume (60 m³) and area (94 m²). [Simulate Mono](../components/CA_Simulate_Mono.md) traces 10000 rays with
   image sources up to order 3 and air absorption; the seed 42 makes the run repeatable. It runs in the background,
   in the worker, when its Run button is pressed.
6. **Analysis.** [Analyse Impulse Response](../components/CA_Analyse_IR.md) takes the responses straight from Simulate
   and derives the room acoustic parameters of the pair its Source and Receiver dropdowns choose: source to
   receiver. [Plot 2D](../components/CA_Plot_2D.md), with its dropdown on T30, draws it.
7. **Auralisation.** [Auralise](../components/CA_Auralise.md) takes the same responses, the same two dropdowns and
   a sound chosen on its Anechoic sound dropdown, such as the bundled Female speech; the
   [Audio Player](../components/CA_Audio_Player.md) plays the result.

The values differ slightly from the Python version's. Ray tracing is random, and the order in which each wall lists
its corners changes which rays the seed draws; the differences are of the same size as those between two seeds.
