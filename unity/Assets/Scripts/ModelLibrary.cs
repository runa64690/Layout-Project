using System;
using UnityEngine;

namespace FurnitureLayout
{
    [CreateAssetMenu(menuName = "Furniture Layout/Model Library")]
    public sealed class ModelLibrary : ScriptableObject
    {
        [Serializable] public class Entry
        {
            public string modelId;
            public GameObject prefab;
            [Tooltip("Correct the model's authored forward/up axes before fitting its bounds.")]
            public Vector3 rotationCorrection;
        }
        public Entry[] entries = Array.Empty<Entry>();
        public Entry Find(string id) => Array.Find(entries, e => e.modelId == id && e.prefab != null);
    }
}
