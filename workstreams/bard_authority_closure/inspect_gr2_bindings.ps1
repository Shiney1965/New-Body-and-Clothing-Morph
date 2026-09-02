param(
    [Parameter(Mandatory=$true)][string]$Source,
    [Parameter(Mandatory=$true)][string]$ExpectedSourceSha256
)
$ErrorActionPreference = 'Stop'
$authorityLibrary = 'C:\bg3-sidecar-work\Tools\LSLib.dll'
$authorityExpectedLibrary = '5DFE246B93CBC95531E011DBF18478C665A9DE4F922F8B4A2B73DA5A865C76D0'
if ((Get-FileHash -LiteralPath $authorityLibrary -Algorithm SHA256).Hash -ne $authorityExpectedLibrary) {
    throw 'GR2_LIBRARY_HASH_MISMATCH'
}
if ((Get-FileHash -LiteralPath $Source -Algorithm SHA256).Hash -ne $ExpectedSourceSha256) {
    throw 'GR2_SOURCE_HASH_MISMATCH'
}
[System.Reflection.Assembly]::LoadFrom($authorityLibrary) | Out-Null
$authorityStream = [IO.File]::OpenRead($Source)
$authorityReader = $null
try {
    $authorityReader = [LSLib.Granny.GR2.GR2Reader]::new($authorityStream)
    $authorityRoot = [LSLib.Granny.Model.Root]::new()
    $authorityReader.Read($authorityRoot)
    $authorityMeshes = @(foreach ($authorityMesh in $authorityRoot.Meshes) {
        $authorityGroups = @(foreach ($authorityGroup in $authorityMesh.PrimaryTopology.Groups) {
            [ordered]@{ material_index=$authorityGroup.MaterialIndex; triangle_first=$authorityGroup.TriFirst; triangle_count=$authorityGroup.TriCount }
        })
        $authorityFormat = [ordered]@{}
        if ($null -ne $authorityMesh.VertexFormat) {
            foreach ($authorityField in $authorityMesh.VertexFormat.GetType().GetFields()) {
                $authorityValue = $authorityField.GetValue($authorityMesh.VertexFormat)
                $authorityFormat[$authorityField.Name] = if ($authorityValue -is [Enum]) { $authorityValue.ToString() } else { $authorityValue }
            }
        }
        [ordered]@{
            name=$authorityMesh.Name
            vertices=$authorityMesh.PrimaryVertexData.Vertices.Count
            indices32=$authorityMesh.PrimaryTopology.Indices.Count
            indices16=$authorityMesh.PrimaryTopology.Indices16.Count
            topology_groups=$authorityGroups
            material_bindings=@(foreach ($authorityBinding in $authorityMesh.MaterialBindings) { if ($null -eq $authorityBinding.Material) { $null } else { $authorityBinding.Material.Name } })
            bone_bindings=@(foreach ($authorityBinding in $authorityMesh.BoneBindings) { $authorityBinding.BoneName })
            vertex_component_names=@(foreach ($authorityComponent in $authorityMesh.PrimaryVertexData.VertexComponentNames) { $authorityComponent.String })
            vertex_format=$authorityFormat
            extended=[ordered]@{ lod=$authorityMesh.ExtendedData.LOD; cloth=$authorityMesh.ExtendedData.Cloth; rigid=$authorityMesh.ExtendedData.Rigid; user_defined_properties=$authorityMesh.ExtendedData.UserDefinedProperties }
        }
    })
    $authorityModels = @(foreach ($authorityModel in $authorityRoot.Models) {
        [ordered]@{ name=$authorityModel.Name; mesh_binding_indices=@(foreach ($authorityBinding in $authorityModel.MeshBindings) { $authorityRoot.Meshes.IndexOf($authorityBinding.Mesh) }) }
    })
    $authoritySkeletons = @(foreach ($authoritySkeleton in $authorityRoot.Skeletons) {
        [ordered]@{ name=$authoritySkeleton.Name; bones=@(foreach ($authorityBone in $authoritySkeleton.Bones) { [ordered]@{name=$authorityBone.Name; parent_index=$authorityBone.ParentIndex} }) }
    })
    $authorityResult = [ordered]@{
        source_sha256=$ExpectedSourceSha256
        reader_library_sha256=$authorityExpectedLibrary
        mesh_count=$authorityRoot.Meshes.Count
        material_count=$authorityRoot.Materials.Count
        models=$authorityModels
        meshes=$authorityMeshes
        skeletons=$authoritySkeletons
        scope='Direct GR2 structure read only; does not write or convert the source.'
    }
} finally {
    if ($null -ne $authorityReader) { $authorityReader.Dispose() }
    $authorityStream.Dispose()
}
if ((Get-FileHash -LiteralPath $Source -Algorithm SHA256).Hash -ne $ExpectedSourceSha256) {
    throw 'GR2_SOURCE_CHANGED_DURING_READ'
}
$authorityResult | ConvertTo-Json -Depth 40 -Compress
