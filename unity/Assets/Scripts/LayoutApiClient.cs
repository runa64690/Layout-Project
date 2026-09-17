using System;
using System.Collections;
using System.Text;
using UnityEngine;
using UnityEngine.Networking;

namespace FurnitureLayout
{
    public sealed class LayoutApiClient : MonoBehaviour
    {
        public string BaseUrl = "http://127.0.0.1:8000";
        public IEnumerator Get<T>(string path, Action<T> done, Action<string> failed) => Send<T>("GET", path, null, done, failed);
        public IEnumerator Post<T>(string path, object body, Action<T> done, Action<string> failed) => Send<T>("POST", path, JsonUtility.ToJson(body), done, failed);
        IEnumerator Send<T>(string method, string path, string json, Action<T> done, Action<string> failed)
        {
            using (var request = new UnityWebRequest(BaseUrl.TrimEnd('/') + "/api/v1/" + path, method))
            {
                request.downloadHandler = new DownloadHandlerBuffer();
                request.timeout = 30;
                if (json != null)
                {
                    request.uploadHandler = new UploadHandlerRaw(Encoding.UTF8.GetBytes(json));
                    request.SetRequestHeader("Content-Type", "application/json");
                }
                yield return request.SendWebRequest();
                if (request.result != UnityWebRequest.Result.Success)
                {
                    failed($"HTTP {request.responseCode}: {request.error}\n{request.downloadHandler.text}");
                    yield break;
                }
                T result;
                try { result = JsonUtility.FromJson<T>(request.downloadHandler.text); }
                catch (Exception e) { failed("Invalid server response: " + e.Message); yield break; }
                if (result == null) { failed("Empty server response"); yield break; }
                done(result);
            }
        }
    }
}
