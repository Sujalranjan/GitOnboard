from pydantic import BaseModel, Field
from typing import List, Dict, Set, Optional

class RepositoryMetadata(BaseModel):
    commit_hash: Optional[str] = Field(None, description="The HEAD commit hash.")
    commit_timestamp: Optional[str] = Field(None, description="The timestamp of the HEAD commit.")
    branch: Optional[str] = Field(None, description="The current active branch name.")
    remote_url: Optional[str] = Field(None, description="The remote URL of the repository (e.g. origin).")

class RepositoryFile(BaseModel):
    path: str = Field(..., description="The path of the file relative to the repository root.")
    name: str = Field(..., description="The name of the file.")
    extension: str = Field(..., description="The file extension (e.g. '.py', '.ts').")
    size: int = Field(..., description="The size of the file in bytes.")
    language: str = Field("Unknown", description="The detected programming language.")

class Package(BaseModel):
    path: str = Field(..., description="The directory path containing the package.")
    name: str = Field(..., description="The name of the package/module if determinable.")
    type: str = Field(..., description="The package type (e.g. 'npm', 'pip', 'cargo').")

class RepositoryManifest(BaseModel):
    metadata: RepositoryMetadata = Field(default_factory=RepositoryMetadata, description="Git metadata for the repository.")
    primary_language: str = Field("Unknown", description="The dominant programming language in the repository.")
    frameworks: List[str] = Field(default_factory=list, description="Detected frameworks (e.g., FastAPI, Flask).")
    files: List[RepositoryFile] = Field(default_factory=list, description="All discovered non-ignored files.")
    languages: List[str] = Field(default_factory=list, description="All languages detected in the repository.")
    packages: List[Package] = Field(default_factory=list, description="All discovered sub-packages or workspaces.")
