import React from "react";
import PackageSearchResults from "../components/PackageSearchResults";
import { FetchKeywordSearchResults } from "../tools/RemoteData";

class KeywordSearchResultPage extends React.Component {
	constructor(props) {
		super(props);
		this.state = {
			processing: false,
			searchResults: [],
		};
	}
	fetchSearchResults() {
		this.setState({ processing: true });
		let params = new URLSearchParams(this.props.location.search);
		const query = params.get("query");
		const hosts = this.props.selectedOriginalHosts.map(
			(h) => h.original_host
		);
		const formats = this.props.selectedDataFormats.map((f) => f.format);
		FetchKeywordSearchResults(query, hosts, formats, (results) => {
			this.setState({
				searchResults: results,
				processing: false,
			});
		});
	}
	componentDidMount() {
		this.fetchSearchResults();
	}
	componentDidUpdate(prevProps) {
		if (
			this.props.location !== prevProps.location ||
			this.props.selectedOriginalHosts !==
				prevProps.selectedOriginalHosts ||
			this.props.selectedDataFormats !== prevProps.selectedDataFormats
		) {
			this.fetchSearchResults();
		}
	}
	render() {
		return (
			<PackageSearchResults
				processing={this.state.processing}
				searchResults={this.state.searchResults}
				originalHosts={this.props.originalHosts}
				dataFormats={this.props.dataFormats}
				selectedOriginalHosts={this.props.selectedOriginalHosts}
				selectedDataFormats={this.props.selectedDataFormats}
				onClickSelectOriginalHost={this.props.onClickSelectOriginalHost}
				onClickUnselectOriginalHost={
					this.props.onClickUnselectOriginalHost
				}
				onClickSelectDataFormat={this.props.onClickSelectDataFormat}
				onClickUnselectDataFormat={this.props.onClickUnselectDataFormat}
				onClickPin={this.props.onClickPin}
				isPinned={this.props.isPinned}
				onPackageLoad={this.props.onPackageLoad}
			/>
		);
	}
}

export default KeywordSearchResultPage;
