import React from "react";
import { Spinner, Container, Row } from "react-bootstrap";
import FilterBar from "./FilterBar.js";
import PackageCardColumn from "./PackageCardColumn.js";
import PackageDetail from "./PackageDetail.js";
import { isMobile } from "react-device-detect";
import { withRouter } from "react-router-dom";

class PackageSearchResults extends React.Component {
	constructor(props) {
		super(props);
		this.state = {
			selectedPacId: null,
		};
	}
	handleSelectPackageCard(pacId) {
		if (isMobile) {
			this.props.history.push("/package/" + pacId);
		} else {
			this.setState({ selectedPacId: pacId });
		}
	}
	render() {
		const hosts = this.props.originalHosts.map((h) => {
			var selected = this.props.selectedOriginalHosts
				.map((host) => host.original_host)
				.includes(h.original_host);
			return {
				key: h.original_host,
				name: h.original_host_display_name,
				region: h.original_host_region,
				selected: selected,
			};
		});
		const formats = this.props.dataFormats.map((h) => {
			var selected = this.props.selectedDataFormats
				.map((f) => f.format)
				.includes(h.format);
			return {
				key: h.format,
				name: h.format,
				selected: selected,
			};
		});
		let selectedPacId;
		if (
			!this.state.selectedPacId &&
			this.props.searchResults &&
			this.props.searchResults.length > 0
		) {
			selectedPacId = this.props.searchResults[0].id;
		} else {
			selectedPacId = this.state.selectedPacId;
		}
		return (
			<Container fluid>
				<Row>
					<div className="col-md-4 search-results">
						<FilterBar
							className="filter-bar sticky-top navbar-light navbar-expanded-sm bg-light border rounded-bottom shadow-sm"
							title="Filter by FileType"
							filters={formats}
							onClickSelectFilter={
								this.props.onClickSelectDataFormat
							}
							onClickUnselectFilter={
								this.props.onClickUnselectDataFormat
							}
						/>
						<div className="pt-4">
							<div
								className={
									this.props.processing
										? "processing-loading"
										: "processing-done"
								}
							>
								<div className="d-flex justify-content-center my-10 py-10">
									<Spinner animation="border" role="status">
										<span className="sr-only">
											Loading...
										</span>
									</Spinner>
								</div>
							</div>
							<PackageCardColumn
								packages={this.props.searchResults}
								onClickPackageCard={this.handleSelectPackageCard.bind(
									this
								)}
								onClickSelectOriginalHost={
									this.props.onClickSelectOriginalHost
								}
								onClickPin={this.props.onClickPin}
								isPinned={this.props.isPinned}
								isHighlighted={this.props.isHighlighted}
							/>
						</div>
					</div>
					<div className="col-md-8 d-none d-md-block package-details">
						<PackageDetail
							pacId={selectedPacId}
							onLoad={this.props.onPackageLoad}
							onClickPin={this.props.onClickPin}
							isPinned={this.props.isPinned}
						/>
					</div>
				</Row>
			</Container>
		);
	}
}

export default withRouter(PackageSearchResults);
