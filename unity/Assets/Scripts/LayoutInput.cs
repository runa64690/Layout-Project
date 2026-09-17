using System;
using UnityEngine;
using UnityEngine.EventSystems;

namespace FurnitureLayout
{
    public sealed class LayoutInput : MonoBehaviour
    {
        public LayoutState State;
        public LayoutRenderer View;
        public Camera Camera;
        public string SelectedKey, SelectedOpening;
        public Action<string> SelectionChanged;
        public Action<string> Message;
        Placement drag;
        Vector2Int grabOffset;
        bool pressed;
        Vector2 previous;
        float yaw = 0, pitch = 55, distance = 5;
        Vector3 target;
        public void FrameRoom()
        {
            float w=State.Data.room.grid_w*State.Catalog.cell_size_m, h=State.Data.room.grid_h*State.Catalog.cell_size_m;
            target=new Vector3(w/2,0,h/2); distance=Mathf.Max(w,h)*1.6f;
        }
        bool OverUI(int finger = -1) => EventSystem.current != null && (finger < 0 ? EventSystem.current.IsPointerOverGameObject() : EventSystem.current.IsPointerOverGameObject(finger));
        void LateUpdate()
        {
            if (State == null) return;
            Camera.transform.position = target + Quaternion.Euler(pitch,yaw,0)*new Vector3(0,0,-distance);
            Camera.transform.LookAt(target);
        }
        void Update()
        {
            if (State == null) return;
            if (Input.touchCount >= 2)
            {
                CancelDrag();
                var a=Input.GetTouch(0); var b=Input.GetTouch(1);
                if (OverUI(a.fingerId) || OverUI(b.fingerId)) return;
                float current=Vector2.Distance(a.position,b.position);
                float old=Vector2.Distance(a.position-a.deltaPosition,b.position-b.deltaPosition);
                distance=Mathf.Clamp(distance-(current-old)*.008f,1.5f,40);
                yaw+=(a.deltaPosition.x+b.deltaPosition.x)*.12f;
                pitch=Mathf.Clamp(pitch-(a.deltaPosition.y+b.deltaPosition.y)*.08f,20,85);
                return;
            }
            if (Input.touchCount == 1)
            {
                var t=Input.GetTouch(0);
                if (t.phase==TouchPhase.Began && !OverUI(t.fingerId)) Begin(t.position);
                if (pressed && (t.phase==TouchPhase.Moved || t.phase==TouchPhase.Stationary)) Move(t.position);
                if (t.phase==TouchPhase.Ended) End(t.position, OverUI(t.fingerId));
                if (t.phase==TouchPhase.Canceled) CancelDrag();
                return;
            }
            if (!OverUI())
            {
                distance=Mathf.Clamp(distance-Input.mouseScrollDelta.y*.3f,1.5f,40);
                if (Input.GetMouseButton(1))
                {
                    yaw+=(Input.mousePosition.x-previous.x)*.3f;
                    pitch=Mathf.Clamp(pitch-(Input.mousePosition.y-previous.y)*.3f,20,85);
                }
                if (Input.GetMouseButtonDown(0)) Begin(Input.mousePosition);
            }
            if (pressed && Input.GetMouseButton(0)) Move(Input.mousePosition);
            if (Input.GetMouseButtonUp(0)) End(Input.mousePosition,OverUI());
            previous=Input.mousePosition;
        }
        Vector2Int Point(Vector2 screen)
        {
            var ray=Camera.ScreenPointToRay(screen);
            if (new Plane(Vector3.up,Vector3.zero).Raycast(ray,out float enter)) return GridCoordinates.Cell(ray.GetPoint(enter),State.Catalog.cell_size_m);
            return new Vector2Int(-100,-100);
        }
        void Begin(Vector2 screen)
        {
            pressed=true;
            if (SelectedOpening != null) return;
            var cell=Point(screen); grabOffset=Vector2Int.zero;
            if (Physics.Raycast(Camera.ScreenPointToRay(screen),out var hit) && hit.collider.TryGetComponent<FurnitureHit>(out var furniture))
            {
                SelectedKey=furniture.Key; SelectionChanged?.Invoke(SelectedKey);
                var p=State.Find(SelectedKey);
                grabOffset=cell-new Vector2Int(p.gx,p.gy);
            }
            if (SelectedKey == null) return;
            drag=State.Find(SelectedKey).Copy(); drag.placed=true; Move(screen);
        }
        void Move(Vector2 screen)
        {
            if (drag == null) return;
            var cell=Point(screen)-grabOffset; drag.gx=cell.x; drag.gy=cell.y;
            View.Preview(drag,State.CanPlace(drag,State.Data.placements));
        }
        void End(Vector2 screen, bool overUI)
        {
            if (!pressed) return;
            if (!overUI && SelectedOpening != null)
            {
                var p=Point(screen); var room=State.Data.room;
                int nearest=Mathf.Min(Mathf.Abs(p.x),Mathf.Abs(p.x-room.grid_w),Mathf.Abs(p.y),Mathf.Abs(p.y-room.grid_h));
                string wall=nearest==Mathf.Abs(p.x) ? "LEFT" : nearest==Mathf.Abs(p.x-room.grid_w) ? "RIGHT" : nearest==Mathf.Abs(p.y) ? "BOTTOM" : "TOP";
                if (!State.MoveOpening(SelectedOpening,wall,wall=="LEFT"||wall=="RIGHT" ? p.y : p.x)) Message?.Invoke("Opening does not fit, overlaps another opening, or blocks furniture.");
            }
            else if (!overUI && drag != null)
            {
                Move(screen);
                if (!State.Place(drag)) Message?.Invoke("Cannot place here: outside room, overlap, or door clearance.");
            }
            CancelDrag();
        }
        void CancelDrag() { pressed=false; drag=null; View.ClearPreview(); }
        public void Rotate()
        {
            if (SelectedKey == null) return;
            var p=State.Find(SelectedKey).Copy(); p.rotation=(p.rotation+1)%4;
            if (p.placed) { if (!State.Place(p)) Message?.Invoke("Rotation would overlap or leave the room."); }
            else { State.Find(SelectedKey).rotation=p.rotation; State.Touch(); }
        }
        void OnApplicationFocus(bool focused) { if (!focused && View != null) CancelDrag(); }
    }
}
