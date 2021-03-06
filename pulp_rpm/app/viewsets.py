from drf_yasg.utils import swagger_auto_schema
from rest_framework import viewsets, mixins
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, MultiPartParser

from pulpcore.plugin.tasking import enqueue_with_reservation
from pulpcore.plugin.serializers import (
    AsyncOperationResponseSerializer,
    RepositorySyncURLSerializer
)
from pulpcore.plugin.viewsets import (
    BaseDistributionViewSet,
    ContentFilter,
    OperationPostponedResponse,
    PublicationViewSet,
    ReadOnlyContentViewSet,
    RemoteViewSet,
    SingleArtifactContentUploadViewSet,
)

from pulp_rpm.app import tasks
from pulp_rpm.app.models import (
    DistributionTree,
    Package,
    RepoMetadataFile,
    RpmDistribution,
    RpmRemote,
    RpmPublication,
    UpdateRecord,
    Modulemd,
    ModulemdDefaults
)
from pulp_rpm.app.serializers import (
    CopySerializer,
    DistributionTreeSerializer,
    MinimalPackageSerializer,
    MinimalUpdateRecordSerializer,
    ModulemdDefaultsSerializer,
    ModulemdSerializer,
    PackageSerializer,
    RepoMetadataFileSerializer,
    RpmDistributionSerializer,
    RpmRemoteSerializer,
    RpmPublicationSerializer,
    UpdateRecordSerializer,
)


class PackageFilter(ContentFilter):
    """
    FilterSet for Package.
    """

    class Meta:
        model = Package
        fields = {
            'name': ['exact', 'in'],
            'epoch': ['exact', 'in'],
            'version': ['exact', 'in'],
            'release': ['exact', 'in'],
            'arch': ['exact', 'in'],
            'pkgId': ['exact', 'in'],
            'checksum_type': ['exact', 'in'],
        }


class PackageViewSet(SingleArtifactContentUploadViewSet):
    """
    A ViewSet for Package.

    Define endpoint name which will appear in the API endpoint for this content type.
    For example::
        http://pulp.example.com/pulp/api/v3/content/rpm/packages/

    Also specify queryset and serializer for Package.
    """

    endpoint_name = 'packages'
    queryset = Package.objects.prefetch_related("_artifacts")
    serializer_class = PackageSerializer
    minimal_serializer_class = MinimalPackageSerializer
    filterset_class = PackageFilter


class RpmRemoteViewSet(RemoteViewSet):
    """
    A ViewSet for RpmRemote.
    """

    endpoint_name = 'rpm'
    queryset = RpmRemote.objects.all()
    serializer_class = RpmRemoteSerializer

    @swagger_auto_schema(
        operation_description="Trigger an asynchronous task to sync RPM content.",
        operation_summary="Sync from remote",
        responses={202: AsyncOperationResponseSerializer}
    )
    @action(detail=True, methods=['post'], serializer_class=RepositorySyncURLSerializer)
    def sync(self, request, pk):
        """
        Dispatches a sync task.
        """
        remote = self.get_object()
        serializer = RepositorySyncURLSerializer(
            data=request.data,
            context={'request': request}
        )
        serializer.is_valid(raise_exception=True)
        repository = serializer.validated_data.get('repository')

        result = enqueue_with_reservation(
            tasks.synchronize,
            [repository, remote],
            kwargs={
                'remote_pk': remote.pk,
                'repository_pk': repository.pk
            }
        )
        return OperationPostponedResponse(result, request)


class UpdateRecordFilter(ContentFilter):
    """
    FilterSet for UpdateRecord.
    """

    class Meta:
        model = UpdateRecord
        fields = {
            'id': ['exact', 'in'],
            'status': ['exact', 'in'],
            'severity': ['exact', 'in'],
            'type': ['exact', 'in'],
        }


class UpdateRecordViewSet(SingleArtifactContentUploadViewSet):
    """
    A ViewSet for UpdateRecord.

    Define endpoint name which will appear in the API endpoint for this content type.
    For example::
        http://pulp.example.com/pulp/api/v3/content/rpm/advisories/

    Also specify queryset and serializer for UpdateRecord.
    """

    endpoint_name = 'advisories'
    queryset = UpdateRecord.objects.all()
    serializer_class = UpdateRecordSerializer
    minimal_serializer_class = MinimalUpdateRecordSerializer
    filterset_class = UpdateRecordFilter


class RpmPublicationViewSet(PublicationViewSet):
    """
    ViewSet for Rpm Publications.
    """

    endpoint_name = 'rpm'
    queryset = RpmPublication.objects.all()
    serializer_class = RpmPublicationSerializer

    @swagger_auto_schema(
        operation_description="Trigger an asynchronous task to create a new RPM "
                              "content publication.",
        responses={202: AsyncOperationResponseSerializer}
    )
    def create(self, request):
        """
        Dispatches a publish task.
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        repository_version = serializer.validated_data.get('repository_version')

        result = enqueue_with_reservation(
            tasks.publish,
            [repository_version.repository],
            kwargs={
                'repository_version_pk': repository_version.pk
            }
        )
        return OperationPostponedResponse(result, request)


class RpmDistributionViewSet(BaseDistributionViewSet):
    """
    ViewSet for RPM Distributions.
    """

    endpoint_name = 'rpm'
    queryset = RpmDistribution.objects.all()
    serializer_class = RpmDistributionSerializer


class CopyViewSet(viewsets.ViewSet):
    """
    ViewSet for Content Copy.
    """

    serializer_class = CopySerializer
    parser_classes = (MultiPartParser, FormParser)

    @swagger_auto_schema(
        operation_description="Trigger an asynchronous task to copy RPM content"
                              "from one repository into another, creating a new"
                              "repository version.",
        operation_summary="Copy content",
        operation_id="copy_content",
        request_body=CopySerializer,
        responses={202: AsyncOperationResponseSerializer}
    )
    def create(self, request):
        """Copy content."""
        serializer = CopySerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)

        source_repo = serializer.validated_data['source_repo']
        source_repo_version = serializer.validated_data['source_repo_version']
        dest_repo = serializer.validated_data['dest_repo']
        types = serializer.validated_data['types']

        async_result = enqueue_with_reservation(
            tasks.copy_content, [source_repo, dest_repo],
            args=[source_repo_version.pk, dest_repo.pk, types],
            kwargs={}
        )
        return OperationPostponedResponse(async_result, request)


class DistributionTreeViewSet(ReadOnlyContentViewSet,
                              mixins.DestroyModelMixin):
    """
    Distribution Tree Viewset.

    """

    endpoint_name = 'distribution_trees'
    queryset = DistributionTree.objects.all()
    serializer_class = DistributionTreeSerializer


class RepoMetadataFileViewSet(ReadOnlyContentViewSet,
                              mixins.DestroyModelMixin):
    """
    RepoMetadataFile Viewset.

    """

    endpoint_name = 'repo_metadata_files'
    queryset = RepoMetadataFile.objects.all()
    serializer_class = RepoMetadataFileSerializer


class ModulemdViewSet(SingleArtifactContentUploadViewSet):
    """
    ViewSet for Modulemd.
    """

    endpoint_name = 'modulemd'
    queryset = Modulemd.objects.all()
    serializer_class = ModulemdSerializer


class ModulemdDefaultsViewSet(SingleArtifactContentUploadViewSet):
    """
    ViewSet for Modulemd.
    """

    endpoint_name = 'modulemd-defaults'
    queryset = ModulemdDefaults.objects.all()
    serializer_class = ModulemdDefaultsSerializer
