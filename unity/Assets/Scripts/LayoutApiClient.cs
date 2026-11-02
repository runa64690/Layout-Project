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
                    Debug.LogWarning($"HTTP {request.responseCode}: {request.error}\n{request.downloadHandler.text}");
                    if (request.responseCode==0)
                        failed("サーバーに接続できません。APIの起動と接続先、ネットワークを確認してください。");
                    else if (request.responseCode==404)
                        failed("接続先または探索結果が見つかりません。結果が期限切れの場合は再探索してください。");
                    else if (request.responseCode==503)
                        failed("サーバーが混み合っています。しばらく待ってから再実行してください。");
                    else failed(LayoutJapanese.ServerError(request.downloadHandler.text)+$"（HTTP {request.responseCode}）");
                    yield break;
                }
                T result;
                try { result = JsonUtility.FromJson<T>(request.downloadHandler.text); }
                catch (Exception e) { Debug.LogWarning(e); failed("サーバーの応答を読み取れませんでした。接続先とAPIの版を確認してください。"); yield break; }
                if (result == null) { failed("サーバーから空の応答が返されました。再実行してください。"); yield break; }
                done(result);
            }
        }
    }
}
