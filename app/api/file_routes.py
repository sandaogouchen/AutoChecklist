"""文件管理 API。"""

from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import Response

from app.domain.file_models import StoredFile
from app.services.file_service import FileService

router = APIRouter(prefix="/api/v1/files", tags=["files"])


def _get_file_service(request: Request) -> FileService:
    return request.app.state.file_service


@router.post("", status_code=201, response_model=StoredFile)
async def upload_file(
    file: UploadFile = File(...),
    file_service: FileService = Depends(_get_file_service),
) -> StoredFile:
    content = await file.read()
    stored = file_service.create_file(
        file_name=file.filename or "upload.bin",
        content=content,
        content_type=file.content_type,
    )
    await file.close()
    return stored


@router.get("", response_model=list[StoredFile])
def list_files(
    file_service: FileService = Depends(_get_file_service),
) -> list[StoredFile]:
    return file_service.list_files()


@router.get("/{file_id}", response_model=StoredFile)
def get_file(
    file_id: str,
    file_service: FileService = Depends(_get_file_service),
) -> StoredFile:
    stored = file_service.get_file(file_id)
    if stored is None:
        raise HTTPException(status_code=404, detail=f"文件未找到: {file_id}")
    return stored


@router.get("/{file_id}/content")
def download_file(
    file_id: str,
    file_service: FileService = Depends(_get_file_service),
) -> Response:
    record = file_service.get_file_content(file_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"文件未找到: {file_id}")

    disposition = f"attachment; filename*=UTF-8''{quote(record.file_name)}"
    return Response(
        content=record.content,
        media_type=record.content_type,
        headers={"Content-Disposition": disposition},
    )


@router.delete("/{file_id}", status_code=204)
def delete_file(
    file_id: str,
    file_service: FileService = Depends(_get_file_service),
):
    deleted = file_service.delete_file(file_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"文件未找到: {file_id}")
    return None
